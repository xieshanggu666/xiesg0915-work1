# IFC 建筑模型核查工具

读取 IFC 文件中的**墙体、门、窗、房间**，自动完成三类核查并导出报告：

1. **未闭合的墙**
   - 自由墙端：墙端头在容差范围内没有与任何墙体连接；
   - 墙段缺口：两段墙端头相对但没有搭接，量化缺口长度；
   - 房间围护缺口：逐房间检查边界，找出没有被墙 / 门覆盖的开口段。
2. **重复构件**：同类型构件形心重合（默认 80mm）且几何一致（体积比 / 轮廓 IoU），
   通过并查集聚类成组，输出每组的全部 GlobalId。
3. **房间净面积清单**：优先采用 `Qto_SpaceBaseQuantities.NetFloorArea`
   声明值，缺失时由房间平面几何计算；并校验声明值与几何值偏差（默认 >2% 警告），
   统计每个房间的门、窗数量与围护闭合状态。

结果支持：

- **点击问题定位构件**：GUI 中点击问题列表，三维视图高亮对应构件并缩放到该位置；
  也可一键在 PyVista 交互窗口中打开（可旋转、缩放、点选）。
- **导出表格**：Excel（汇总 / 问题清单 / 房间净面积 / 重复构件 4 张表）、CSV、JSON。
- **导出标注图**：平面标注图（问题编号 + 红线标出围护缺口）与三维标注图。

## 安装

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# GUI 需要系统 Python 带 tkinter（Debian/Ubuntu：sudo apt install python3-tk）
```

中文字体：项目 `fonts/` 目录可放置 `NotoSansSC.ttf`，程序会自动注册；
否则尝试使用系统已装的中文字体（微软雅黑 / 黑体 / 文泉驿等）。

## 命令行用法

```bash
# 核查并导出全部报告到 output/
python -m ifc_audit.cli audit path/to/model.ifc -o output/

# CI 场景：存在错误级问题时退出码为 1
python -m ifc_audit.cli audit model.ifc --fail-on-error -q

# 图形界面（浏览文件、点击定位、导出）
python -m ifc_audit.cli gui
```

输出文件（以模型名 `sample` 为例）：

| 文件 | 内容 |
| --- | --- |
| `sample_核查报告.xlsx` | 汇总、问题清单、房间净面积、重复构件四张表 |
| `sample_问题清单.csv` / `sample_房间净面积.csv` | 对应表格的 CSV |
| `sample_标注平面图.png` | 平面图：墙/房间/门窗 + 问题编号 + 围护缺口红线 |
| `sample_三维标注.png` | 三维轴测标注图（无 GPU 环境自动用 matplotlib 渲染） |
| `sample_结果.json` | 机器可读的完整结果 |

## 图形界面

`python -m ifc_audit.cli gui` 打开窗口：

- 顶部选择 IFC 文件并执行核查；
- 左侧「问题清单」按严重程度着色（红=错误 / 黄=警告 / 蓝=提示），
  点击任意一条，右侧三维视图高亮关联构件并缩放定位，下方显示详情与 GlobalId；
- 「房间净面积」标签页给出每个房间的面积、来源、门窗数与闭合状态，
  点击可在三维中定位房间；
- 「在 PyVista 中打开」启动独立的 PyVista 交互窗口（与 Tk 主循环隔离，
  避免 VTK/Tk 冲突），可旋转缩放查看；
- 「导出到目录…」保存全部表格与标注图。

## 作为 Python 库调用

```python
from ifc_audit.pipeline import audit_ifc
from ifc_audit import report

model = audit_ifc("model.ifc")
print(model.summary())
for issue in model.issues:
    print(issue.issue_id, issue.title, issue.global_ids)
for room in model.rooms:
    print(room.name, room.net_area, "m²", "闭合" if room.enclosed else "有缺口")

report.export_excel(model, "out/报告.xlsx")
report.export_annotated_plan(model, "out/标注图.png")
```

三维定位（桌面环境）：

```python
from ifc_audit.viewer import Viewer3D

viewer = Viewer3D(model)
viewer.locate(issue.global_ids)   # 高亮并把相机对准构件
viewer.run()
```

## 核查方法说明

- **几何提取**：优先解析参数化 `IfcExtrudedAreaSolid` 的二维轮廓
  （矩形 / 任意闭合曲线 / 圆形，支持挤出方向与 RefDirection），
  得到轴对齐的精确平面轮廓，避免 BRep 三角化在顶盖附近产生斜面瑕疵；
  BRep / 曲面等表示回退到「21 个高度水平切片 + shapely polygonize」。
- **墙体围护**：取门楣上方的完整墙身截面（参数化轮廓或最大面积切片），
  与门扇凸包联合后，对每个房间的平面边界做 `difference`；
  未被覆盖且长度超过 100mm 的线段即围护缺口。窗不参与围护（窗台以上为采光面）。
- **自由端 / 缺口**：用 PCA 从墙轮廓求中轴线与端点，
  检查端点是否进入其它墙体 50mm 范围；再把邻近的自由端聚类，
  同一位置出现 ≥2 个不同墙的端头时判为「墙段缺口」，否则为「自由墙端」。
- **重复构件**：同类构件两两比较，形心距 < 80mm、体积比 ≥ 0.85、
  封闭轮廓 IoU ≥ 0.70 即判重，并查集聚类成组。

容差常量集中在 `ifc_audit/checks.py` 顶部，可按项目精度要求调整。

## 生成自带已知问题的样例模型

```bash
python tools/make_sample_ifc.py output/sample.ifc
python -m ifc_audit.cli audit output/sample.ifc -o output/
```

样例中人为注入：1 组重复墙、1 组重复门、1 个室内自由墙垛（2 个自由端）、
1 处 150mm 墙段缺口与对应房间围护缺口、1 个面积偏差房间、1 个无声明面积房间。

## 模块结构

```
ifc_audit/
  units.py       单位换算（项目长度单位 -> 米）
  geometry.py    网格切片、轮廓提取、中轴线/厚度
  analytic.py    参数化 IfcExtrudedAreaSolid 轮廓解析
  extract.py     IFC 提取墙/门/窗/房间
  checks.py      重复构件、自由端、墙段缺口、房间围护
  rooms.py       房间净面积清单
  report.py      Excel / CSV / 平面标注图
  viewer.py      PyVista 三维查看器 + matplotlib 三维回退
  viewer_win.py  独立进程 PyVista 窗口
  gui.py         Tkinter 图形界面
  cli.py         命令行入口
  pipeline.py    流程编排
tools/
  make_sample_ifc.py  样例模型生成
```

## 已知限制

- 核查在二维水平面进行，适用于常规正交墙体；斜墙（挤出方向带水平分量）
  在参数化解析中按 RefDirection 处理，曲面墙的缺口检测精度有限。
- 无 GPU / 无显示的服务器上 PyVista 交互窗口与离屏渲染不可用，
  会自动改用 matplotlib 三维图；表格与平面标注图不受影响。
- 房间-门窗归属按平面距离关联，门位于两个房间边界时会计入两侧。

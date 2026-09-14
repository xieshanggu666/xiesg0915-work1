"""命令行入口。

用法::

    python -m ifc_audit.cli audit model.ifc -o output/
    python -m ifc_audit.cli gui              # 图形界面
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from .pipeline import audit_ifc
from . import report
from .report import KIND_CN, SEV_CN


def _cmd_audit(args) -> int:
    out_dir = args.output
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(args.ifc))[0]

    def progress(pct, msg):
        if not args.quiet:
            print(f"[{pct:3d}%] {msg}", flush=True)

    model = audit_ifc(args.ifc, progress=progress if not args.quiet else None)
    s = model.summary()

    print("\n================ 核查汇总 ================")
    print(f"文件        : {s['file']}")
    print(f"墙体/门/窗  : {s['walls']} / {s['doors']} / {s['windows']}")
    print(f"房间        : {s['rooms']}    净面积合计: {s['total_net_area']} m²")
    print(f"问题        : {s['issues']} 条 (错误 {s['errors']} / 警告 {s['warnings']})")
    print(f"重复构件组  : {s['duplicate_groups']}")

    if model.issues:
        print("\n---------------- 问题清单 ----------------")
        for n, i in enumerate(model.issues, start=1):
            print(f"{n:>3}. {i.issue_id} [{SEV_CN.get(i.severity, i.severity)}] "
                  f"{KIND_CN.get(i.kind, i.kind)} | {i.title}"
                  f"{f'  ({i.storey})' if i.storey else ''}")

    print("\n---------------- 房间净面积 --------------")
    print(f"{'房间':<14}{'楼层':<10}{'净面积m²':>10}{'来源':>8}"
          f"{'门':>4}{'窗':>4}  围护状态")
    for r in model.rooms:
        print(f"{(r.name or '')[:14]:<14}{(r.storey or '')[:10]:<10}"
              f"{r.net_area:>10.2f}{('声明' if r.area_source == 'declared' else '几何'):>8}"
              f"{r.doors:>4}{r.windows:>4}  {r.enclosure_label}")

    outputs = {}
    xlsx = os.path.join(out_dir, f"{base}_核查报告.xlsx")
    report.export_excel(model, xlsx)
    outputs["excel"] = xlsx

    report.export_issues_csv(model, os.path.join(out_dir, f"{base}_问题清单.csv"))
    report.export_rooms_csv(model, os.path.join(out_dir, f"{base}_房间净面积.csv"))
    outputs["issues_csv"] = os.path.join(out_dir, f"{base}_问题清单.csv")
    outputs["rooms_csv"] = os.path.join(out_dir, f"{base}_房间净面积.csv")

    plan = os.path.join(out_dir, f"{base}_标注平面图.png")
    report.export_annotated_plan(model, plan)
    outputs["annotated_plan"] = plan

    # 三维图：优先 pyvista 离屏渲染；无 GL/显示环境自动降级 matplotlib
    view3d = os.path.join(out_dir, f"{base}_三维标注.png")
    try:
        from .viewer import Viewer3D, offscreen_render_available, matplotlib_screenshot
        if offscreen_render_available():
            Viewer3D(model).screenshot(view3d)
        else:
            if not args.quiet:
                print("[info] 当前环境无 GPU/显示，三维图改用 matplotlib 渲染；"
                      "在桌面环境运行 `python -m ifc_audit.cli gui` 可使用 PyVista 交互定位。")
            matplotlib_screenshot(model, view3d)
    except Exception as exc:
        if not args.quiet:
            print(f"[warn] 三维渲染失败（{exc}），改用 matplotlib。")
        from .viewer import matplotlib_screenshot
        matplotlib_screenshot(model, view3d)
    outputs["view3d"] = view3d

    # 机器可读 JSON（GUI / 后续流水线使用）
    dump = {
        "summary": s,
        "issues": [
            {
                "id": i.issue_id, "severity": i.severity, "kind": i.kind,
                "title": i.title, "detail": i.detail,
                "global_ids": i.global_ids,
                "location": list(i.location), "storey": i.storey,
                "measure": i.measure,
            } for i in model.issues
        ],
        "rooms": [vars(r) for r in model.rooms],
        "outputs": outputs,
    }
    json_path = os.path.join(out_dir, f"{base}_结果.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(dump, f, ensure_ascii=False, indent=2, default=str)

    print("\n---------------- 导出文件 ----------------")
    for k, v in outputs.items():
        print(f"{k:<16}: {v}")
    print(f"{'json':<16}: {json_path}")

    return 1 if (s["errors"] > 0 and args.fail_on_error) else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="ifc_audit",
        description="IFC 建筑模型核查工具：未闭合墙 / 重复构件 / 房间净面积",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_audit = sub.add_parser("audit", help="核查 IFC 文件并导出报告")
    p_audit.add_argument("ifc", help="IFC 文件路径 (.ifc/.ifcxml/.ifczip)")
    p_audit.add_argument("-o", "--output", default="output", help="输出目录")
    p_audit.add_argument("-q", "--quiet", action="store_true", help="精简输出")
    p_audit.add_argument("--fail-on-error", action="store_true",
                         help="存在错误级问题时以退出码 1 返回（便于 CI 集成）")
    p_audit.set_defaults(func=_cmd_audit)

    p_gui = sub.add_parser("gui", help="启动图形界面")
    p_gui.set_defaults(func=lambda a: _launch_gui())

    args = parser.parse_args(argv)
    return args.func(args)


def _launch_gui() -> int:
    try:
        from .gui import App
    except Exception as exc:
        print(f"无法启动图形界面：{exc}\n"
              "本机 Python 缺少 tkinter，请安装系统的 python3-tk，"
              "或直接使用 `python -m ifc_audit.cli audit`。", file=sys.stderr)
        return 2
    App().mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

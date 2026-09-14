"""核查数据模型。

所有几何量均投影到建筑水平面（IfcProject 的 XY 平面，通常为 Z 轴法向），
单位统一换算成米。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from shapely.geometry import Polygon, MultiPolygon, LineString

# 支持的 IFC 构件类别
WALL = "IfcWall"
DOOR = "IfcDoor"
WINDOW = "IfcWindow"
SPACE = "IfcSpace"


@dataclass
class Element:
    """提取出的单个构件。"""

    global_id: str
    ifc_type: str
    name: str
    object_type: str = ""
    storey: str = ""

    # 包围盒（世界坐标，米），(minx, miny, minz, maxx, maxy, maxz)
    bounds: tuple[float, float, float, float, float, float] = (0,) * 6
    centroid: np.ndarray = field(default_factory=lambda: np.zeros(3))
    volume: float = 0.0

    # 水平面轮廓（shapely，单位米）；墙/房间均有，门窗可为 None
    footprint: Optional[Polygon | MultiPolygon] = None
    # 封闭洞口的凸包轮廓（重复构件检测用）
    hull: Optional[Polygon] = None

    # 墙体专用：中轴线（含门洞口的墙体会是 None）
    axis: Optional[LineString] = None
    base_elevation: float = 0.0
    height: float = 0.0
    thickness: float = 0.0

    # 墙的厚度方向（水平单位向量），用于自由端判定
    thick_dir: Optional[np.ndarray] = None

    # 围护关系（ifopenshell inverse attr）
    hosted_by_wall: Optional[str] = None  # 门窗所属墙的 GlobalId

    # 原始 IFC 实体（交互定位时用，不参与序列化）
    raw: object = field(default=None, repr=False)

    @property
    def key(self) -> str:
        return f"{self.ifc_type}:{self.global_id}"

    @property
    def label(self) -> str:
        """界面显示名。"""
        cn = {"IfcWall": "墙", "IfcDoor": "门", "IfcWindow": "窗",
              "IfcSpace": "房间"}.get(self.ifc_type, self.ifc_type)
        return f"{cn} | {self.name or '(未命名)'} | {self.global_id[:8]}"


@dataclass
class Issue:
    """一条核查问题。"""

    issue_id: str
    severity: str            # error / warning / info
    kind: str                # 问题类型标识
    title: str               # 一句话描述
    detail: str              # 详细说明
    global_ids: list[str]    # 关联构件（点击定位用）
    location: tuple[float, float]          # 标注图上的位置 (x, y) 米
    storey: str = ""
    measure: float = 0.0     # 量化指标（缺口长度 / 重合体积比等）

    @property
    def label(self) -> str:
        return f"[{self.severity.upper()}] {self.title}"


@dataclass
class RoomArea:
    """房间净面积清单项。"""

    global_id: str
    name: str
    storey: str
    long_name: str
    net_area: float            # 采用的净面积 m²
    declared_area: float       # IFC 中声明的 NetFloorArea（无则 0）
    computed_area: float       # 由几何计算的面积 m²
    area_source: str           # declared / geometry
    deviation: float           # 声明值与计算值相对偏差（无则 0）
    bounds: tuple[float, float, float, float, float, float]
    centroid: tuple[float, float]
    doors: int
    windows: int
    enclosure_status: str      # closed=闭合 / open=不闭合 / unchecked=未检查(无几何)
    perimeter: float
    global_ids_doors: list[str] = field(default_factory=list)
    global_ids_windows: list[str] = field(default_factory=list)

    @property
    def enclosed(self) -> bool:
        """围护闭合（未检查按不闭合处理，仅供布尔判断用）。"""
        return self.enclosure_status == "closed"

    @property
    def enclosure_label(self) -> str:
        return {"closed": "是", "open": "否", "unchecked": "未检查"}.get(
            self.enclosure_status, "未检查")


@dataclass
class AuditModel:
    """一次核查的完整结果。"""

    file_path: str
    unit_scale: float
    elements: dict[str, Element] = field(default_factory=dict)
    issues: list[Issue] = field(default_factory=list)
    rooms: list[RoomArea] = field(default_factory=list)

    # 分析中间数据：房间 -> 围护缺口线段列表
    room_gaps: dict[str, list] = field(default_factory=dict)
    # 重复构件分组
    duplicate_groups: list[list[str]] = field(default_factory=list)

    def by_type(self, ifc_type: str) -> list[Element]:
        return [e for e in self.elements.values() if e.ifc_type == ifc_type]

    def wall_ids(self) -> list[str]:
        return [e.global_id for e in self.by_type(WALL)]

    def summary(self) -> dict:
        n_err = sum(1 for i in self.issues if i.severity == "error")
        n_warn = sum(1 for i in self.issues if i.severity == "warning")
        return {
            "file": self.file_path,
            "walls": len(self.by_type(WALL)),
            "doors": len(self.by_type(DOOR)),
            "windows": len(self.by_type(WINDOW)),
            "rooms": len(self.by_type(SPACE)),
            "issues": len(self.issues),
            "errors": n_err,
            "warnings": n_warn,
            "duplicate_groups": len(self.duplicate_groups),
            "total_net_area": round(sum(r.net_area for r in self.rooms), 3),
        }

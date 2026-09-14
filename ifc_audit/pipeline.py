"""核查流程编排：提取 -> 几何/重复检查 -> 房间面积。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .extract import extract
from .checks import run_all_checks
from .rooms import build_room_areas

if TYPE_CHECKING:
    from .model import AuditModel


def audit_ifc(file_path: str, progress=None) -> "AuditModel":
    """执行完整核查流程。

    Args:
        file_path: IFC 文件路径。
        progress: 可选回调 ``progress(percent: int, message: str)``。
    """
    def report(pct, msg):
        if progress:
            progress(pct, msg)

    report(5, "正在解析 IFC 几何…")
    model = extract(file_path)

    report(55, f"已提取 {len(model.elements)} 个构件，正在执行核查规则…")
    run_all_checks(model)

    report(75, "正在统计房间净面积…")
    build_room_areas(model)

    report(100, "核查完成。")
    return model

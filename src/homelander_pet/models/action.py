from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class DesktopOp:
    op: str
    params: dict = field(default_factory=dict)


@dataclass(slots=True)
class PetAction:
    id: str
    label: str
    media_path: str
    loop: bool = False
    desktop_ops: list[DesktopOp] = field(default_factory=list)

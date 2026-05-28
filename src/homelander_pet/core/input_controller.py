from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class InputController(Protocol):
    def click(self, x: int, y: int, button: str = "left", count: int = 1) -> None: ...

    def move_mouse_to(self, x: int, y: int) -> None: ...

    def drag(self, start: tuple[int, int], end: tuple[int, int]) -> None: ...

    def release_mouse(self) -> None: ...


@dataclass(slots=True)
class NullInputController:
    """Safe fallback used until real automation is wired in."""

    def click(self, x: int, y: int, button: str = "left", count: int = 1) -> None:
        return None

    def move_mouse_to(self, x: int, y: int) -> None:
        return None

    def drag(self, start: tuple[int, int], end: tuple[int, int]) -> None:
        return None

    def release_mouse(self) -> None:
        return None

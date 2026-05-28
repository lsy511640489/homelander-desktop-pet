from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class PetState:
    action_id: str = "idle"
    is_dragging: bool = False
    is_thinking: bool = False
    last_message: str = ""

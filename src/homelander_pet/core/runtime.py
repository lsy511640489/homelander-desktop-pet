from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from homelander_pet.core.action_registry import ActionRecord
from homelander_pet.core.config import PetProfile, load_pet_profile


@dataclass(slots=True)
class PetRuntime:
    profile: PetProfile
    pet_id: str
    actions: dict[str, ActionRecord] = field(default_factory=dict)
    current_action: str = "idle"
    current_media_path: str = ""

    def set_action(self, action_id: str) -> None:
        if action_id not in self.actions:
            raise KeyError(f"unknown action: {action_id}")
        self.current_action = action_id
        self.current_media_path = self.actions[action_id].media_path

    @classmethod
    def from_files(cls, profile_path: Path, project_root: Path) -> "PetRuntime":
        profile = load_pet_profile(profile_path, project_root)
        from homelander_pet.core.action_registry import load_action_records

        records = load_action_records(profile.action_table)
        actions = {record.id: record for record in records}
        runtime = cls(profile=profile, pet_id=profile.pet_id, actions=actions)
        runtime.set_action(profile.avatar.default_action)
        return runtime

    def describe_current_state(self) -> str:
        action = self.actions.get(self.current_action)
        label = action.label if action else self.current_action
        return f"{self.profile.display_name} · {label} · {self.current_media_path}"


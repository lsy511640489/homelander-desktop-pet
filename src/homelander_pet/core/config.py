from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class LLMConfig:
    provider: str = "deepseek"
    model: str = "deepseek-chat"
    base_url: str = "https://api.deepseek.com"


@dataclass(slots=True)
class AvatarConfig:
    format: str = "video"
    default_action: str = "idle"


@dataclass(slots=True)
class PetProfile:
    pet_id: str
    display_name: str
    asset_root: Path
    action_table: Path
    avatar: AvatarConfig
    llm: LLMConfig


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_pet_profile(path: Path, project_root: Path) -> PetProfile:
    resolved_path = path if path.is_absolute() else project_root / path
    payload = _load_json(resolved_path)

    avatar_payload = payload.get("avatar", {})
    llm_payload = payload.get("llm", {})

    asset_root = Path(payload.get("asset_root", "assets/videos"))
    action_table = Path(payload.get("action_table", "config/action-table.example.json"))

    return PetProfile(
        pet_id=payload.get("pet_id", "unknown"),
        display_name=payload.get("display_name", payload.get("pet_id", "pet")),
        asset_root=asset_root if asset_root.is_absolute() else project_root / asset_root,
        action_table=action_table if action_table.is_absolute() else project_root / action_table,
        avatar=AvatarConfig(
            format=avatar_payload.get("format", "video"),
            default_action=avatar_payload.get("default_action", "idle"),
        ),
        llm=LLMConfig(
            provider=llm_payload.get("provider", "deepseek"),
            model=llm_payload.get("model", "deepseek-chat"),
            base_url=llm_payload.get("base_url", "https://api.deepseek.com"),
        ),
    )

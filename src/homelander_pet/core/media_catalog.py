from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class MediaAsset:
    action_id: str
    path: Path
    loop: bool = False


def resolve_media(asset_root: Path, relative_path: str, action_id: str, loop: bool = False) -> MediaAsset:
    return MediaAsset(action_id=action_id, path=asset_root / relative_path, loop=loop)

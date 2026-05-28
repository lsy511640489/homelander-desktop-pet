from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class ActionRecord:
    id: str
    label: str
    media_path: str
    loop: bool = False


def load_action_records(path: Path) -> list[ActionRecord]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    records: list[ActionRecord] = []
    for item in payload.get("actions", []):
        media = item.get("media", {})
        records.append(
            ActionRecord(
                id=item["id"],
                label=item.get("label", item["id"]),
                media_path=media.get("path", ""),
                loop=bool(media.get("loop", False)),
            )
        )
    return records

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from homelander_pet.agent.orchestrator import HomelanderAgent
from homelander_pet.adapters.tk_desktop import DesktopPetWindow
from homelander_pet.core.runtime import PetRuntime


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if not key or key in os.environ:
            continue

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]

        os.environ[key] = value


def resolve_project_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def load_action_table(path: Path) -> dict:
    resolved_path = resolve_project_path(path)
    with resolved_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Homelander Pet runtime")
    parser.add_argument(
        "--profile",
        type=Path,
        default=Path("config/pet-profile.example.json"),
        help="Path to the pet profile JSON",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    load_env_file(PROJECT_ROOT / ".env")
    project_root = PROJECT_ROOT
    runtime = PetRuntime.from_files(resolve_project_path(args.profile), project_root)
    conversation_agent = HomelanderAgent(runtime, project_root)

    if os.environ.get("HOMELANDER_PET_HEADLESS") == "1":
        print(f"pet={runtime.pet_id}")
        print(f"actions={len(runtime.actions)}")
        for action in runtime.actions.values():
            print(f"- {action.id} -> {action.media_path}")
        conversation_agent.close()
        return 0

    app = DesktopPetWindow(runtime, conversation_agent=conversation_agent)
    try:
        app.mainloop()
    finally:
        conversation_agent.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

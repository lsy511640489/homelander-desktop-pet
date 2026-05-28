from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from homelander_pet.adapters.deepseek import DeepSeekClient


@dataclass(slots=True)
class SkillSpec:
    name: str
    entry: Path
    enabled: bool = True
    description: str = ""
    docs: str = ""


@dataclass(slots=True)
class SkillBridge:
    project_root: Path
    llm: DeepSeekClient
    skills: dict[str, SkillSpec] = field(default_factory=dict)
    _tool_to_skill_name: dict[str, str] = field(default_factory=dict)

    @staticmethod
    def _normalize_tool_name(skill_name: str) -> str:
        normalized = re.sub(r"[^0-9A-Za-z_]+", "_", skill_name).strip("_")
        return normalized or "skill"

    @classmethod
    def from_config(cls, project_root: Path, config_path: Path, llm: DeepSeekClient) -> "SkillBridge":
        resolved_path = config_path if config_path.is_absolute() else project_root / config_path
        payload = json.loads(resolved_path.read_text(encoding="utf-8"))
        skills: dict[str, SkillSpec] = {}
        tool_to_skill_name: dict[str, str] = {}
        for item in payload.get("skills", []):
            entry = Path(item.get("entry", ""))
            if not entry.is_absolute():
                entry = project_root / entry
            docs = ""
            skill_doc = entry / "SKILL.md"
            if skill_doc.exists():
                docs = skill_doc.read_text(encoding="utf-8")
            spec = SkillSpec(
                name=item["name"],
                entry=entry,
                enabled=bool(item.get("enabled", True)),
                description=item.get("description", ""),
                docs=docs,
            )
            if spec.enabled:
                skills[spec.name] = spec
                tool_to_skill_name[cls._normalize_tool_name(spec.name)] = spec.name
        return cls(project_root=project_root, llm=llm, skills=skills, _tool_to_skill_name=tool_to_skill_name)

    def tool_definitions(self) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        for spec in self.skills.values():
            tool_name = self._normalize_tool_name(spec.name)
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": f"skill__{tool_name}",
                        "description": spec.description or f"Run skill {spec.name}",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "task": {"type": "string", "description": "What the skill should accomplish"},
                                "input": {"type": "object", "description": "Structured input for the skill", "additionalProperties": True},
                            },
                            "required": ["task"],
                            "additionalProperties": False,
                        },
                    },
                }
            )
        return tools

    def invoke(self, skill_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        resolved_name = self._tool_to_skill_name.get(skill_name, skill_name)
        spec = self.skills.get(resolved_name)
        if spec is None:
            raise KeyError(f"unknown skill: {skill_name}")

        system_prompt = "\n".join(
            [
                f"你正在执行一个名为 {spec.name} 的技能。",
                spec.description or "",
                "下面是技能说明，按它完成任务，不要编造你没有做过的步骤。",
                spec.docs[:6000],
            ]
        ).strip()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]
        response = self.llm.chat(messages)
        content = response["choices"][0]["message"].get("content", "")
        return {"skill": spec.name, "result": content, "status": "ok"}

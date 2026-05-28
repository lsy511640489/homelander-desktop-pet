from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from homelander_pet.adapters.deepseek import DeepSeekClient, DeepSeekConfig
from homelander_pet.adapters.mcp_bridge import MCPBridge
from homelander_pet.adapters.skill_bridge import SkillBridge
from homelander_pet.core.runtime import PetRuntime
from homelander_pet.agent.agent_memory_lib import CompressedAgentMemory
from homelander_pet.agent.agent_memory_lib.memory_storage import set_data_root


@dataclass(slots=True)
class ConversationResult:
    reply: str
    tool_trace: list[str] = field(default_factory=list)


class HomelanderAgent:
    def __init__(
        self,
        runtime: PetRuntime,
        project_root: Path,
        plugins_path: Path | None = None,
    ) -> None:
        self.runtime = runtime
        self.project_root = project_root
        self.plugins_path = plugins_path or Path("config/plugins.example.json")
        set_data_root(str(self.project_root / "agent_memory_data"))
        llm_config = DeepSeekConfig.from_environment(base_url=runtime.profile.llm.base_url, model=runtime.profile.llm.model)
        self.llm = DeepSeekClient(llm_config)
        self.skill_bridge = SkillBridge.from_config(project_root, self.plugins_path, self.llm)
        self.mcp_bridge = MCPBridge.from_config(project_root, self.plugins_path)
        self.memory = CompressedAgentMemory(short_term_max_round=8, daily_compress_level=30)

    def _remember_turn(self, user_text: str, reply: str, tool_trace: list[str]) -> None:
        memory_reply = reply
        if tool_trace:
            tool_summary = "\n".join(f"- {item}" for item in tool_trace)
            memory_reply = f"{reply}\n\n[Tool trace]\n{tool_summary}".strip()
        self.memory.add_chat_round(user_text, memory_reply)

    def close(self) -> None:
        self.mcp_bridge.close()

    def _system_prompt(self) -> str:
        skill_tools = [tool["function"]["name"] for tool in self.skill_bridge.tool_definitions()]
        mcp_tools = [tool["function"]["name"] for tool in self.mcp_bridge.tool_definitions()]
        return "\n".join(
            [
                "You are Homelander, a proud and arrogant person who speaks in English.",
                "You need to communicate with the user naturally, concisely, and accurately",
                "If you need external capabilities, prioritize calling tools and do not fabricate results.",
                "If the user asks for a skill, call the matching skill tool directly instead of answering from memory.",
                f"Current pet state: {self.runtime.describe_current_state()}",
                f"Available skill tools: {', '.join(skill_tools) if skill_tools else 'none'}",
                f"Available MCP tools: {', '.join(mcp_tools) if mcp_tools else 'none'}",
                "Memory system context:",
                self.memory.build_llm_context(),
            ]
        )

    def _tool_definitions(self) -> list[dict[str, Any]]:
        return [*self.skill_bridge.tool_definitions(), *self.mcp_bridge.tool_definitions()]

    def _parse_arguments(self, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if isinstance(value, str) and value.strip():
            return json.loads(value)
        return {}

    def _run_tool(self, tool_call: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        function = tool_call.get("function", {})
        tool_name = function.get("name", "")
        arguments = self._parse_arguments(function.get("arguments"))
        if tool_name.startswith("skill__"):
            skill_name = tool_name.removeprefix("skill__")
            result = self.skill_bridge.invoke(skill_name, arguments)
            return tool_name, result
        if tool_name.startswith("mcp__"):
            result = self.mcp_bridge.invoke(tool_name, arguments)
            return tool_name, result
        raise KeyError(f"unknown tool: {tool_name}")

    def ask(self, user_text: str) -> ConversationResult:
        messages: list[dict[str, Any]] = [{"role": "system", "content": self._system_prompt()}]
        messages.append({"role": "user", "content": user_text})

        tool_trace: list[str] = []
        tools = self._tool_definitions()

        for _ in range(4):
            response = self.llm.chat(messages, tools=tools)
            message = response["choices"][0]["message"]
            tool_calls = message.get("tool_calls") or []
            if tool_calls:
                messages.append(message)
                for tool_call in tool_calls:
                    tool_name, result = self._run_tool(tool_call)
                    tool_trace.append(f"{tool_name}: {result}")
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.get("id", tool_name),
                            "content": json.dumps(result, ensure_ascii=False),
                        }
                    )
                continue

            reply = str(message.get("content", "")).strip() or "我暂时没有可返回的内容。"
            messages.append({"role": "assistant", "content": reply})
            self._remember_turn(user_text, reply, tool_trace)
            return ConversationResult(reply=reply, tool_trace=tool_trace)

        raise RuntimeError("conversation exceeded tool iteration limit")

    def ask_stream(
        self,
        user_text: str,
        on_chunk: Callable[[str], None],
        on_tool_event: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> ConversationResult:
        messages: list[dict[str, Any]] = [{"role": "system", "content": self._system_prompt()}]
        messages.append({"role": "user", "content": user_text})

        tool_trace: list[str] = []
        tools = self._tool_definitions()

        for _ in range(4):
            response = self.llm.chat(messages, tools=tools)
            message = response["choices"][0]["message"]
            tool_calls = message.get("tool_calls") or []
            if tool_calls:
                messages.append(message)
                for tool_call in tool_calls:
                    tool_name, result = self._run_tool(tool_call)
                    tool_trace.append(f"{tool_name}: {result}")
                    if on_tool_event is not None:
                        on_tool_event(tool_name, result)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.get("id", tool_name),
                            "content": json.dumps(result, ensure_ascii=False),
                        }
                    )
                continue

            chunks: list[str] = []
            for chunk in self.llm.chat_stream(messages, tools=None):
                chunks.append(chunk)
                on_chunk(chunk)

            reply = "".join(chunks).strip() or "我暂时没有可返回的内容。"
            messages.append({"role": "assistant", "content": reply})
            self._remember_turn(user_text, reply, tool_trace)
            return ConversationResult(reply=reply, tool_trace=tool_trace)

        raise RuntimeError("conversation exceeded tool iteration limit")
from __future__ import annotations

import threading
import tkinter as tk
from tkinter.scrolledtext import ScrolledText
from typing import Callable

from homelander_pet.agent.orchestrator import HomelanderAgent


class ChatWindow(tk.Toplevel):
    WINDOW_BG = "#07111d"
    SHELL_BG = "#0b1525"
    PANEL_BG = "#111c2d"
    PANEL_EDGE = "#5f7390"
    HISTORY_BG = "#0d1726"
    ENTRY_BG = "#0f1a2a"
    TEXT_FG = "#eef4fb"
    MUTED_FG = "#a8b7cf"
    ACCENT_FG = "#9fd3ff"
    BUTTON_BG = "#dbe7f4"
    BUTTON_ACTIVE_BG = "#f4f8fc"
    BUTTON_FG = "#0b1320"

    def __init__(self, master: tk.Misc, agent: HomelanderAgent, on_pet_action: Callable[[str], None] | None = None) -> None:
        super().__init__(master)
        self.agent = agent
        self.on_pet_action = on_pet_action
        self.title("Homelander Chat")
        self.geometry("560x720")
        self.minsize(500, 620)
        self.resizable(True, True)
        self._busy = False
        self._streaming_reply_active = False

        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.configure(background=self.WINDOW_BG)

        try:
            self.attributes("-alpha", 0.95)
        except tk.TclError:
            pass

        shell = tk.Frame(self, bg=self.SHELL_BG, bd=0, highlightthickness=0)
        shell.pack(fill="both", expand=True, padx=12, pady=12)

        panel_shadow = tk.Frame(shell, bg="#050a12", bd=0, highlightthickness=0)
        panel_shadow.pack(fill="both", expand=True)

        panel = tk.Frame(
            panel_shadow,
            bg=self.PANEL_BG,
            bd=0,
            highlightthickness=1,
            highlightbackground=self.PANEL_EDGE,
            highlightcolor=self.PANEL_EDGE,
        )
        panel.pack(fill="both", expand=True, padx=(0, 2), pady=(0, 2))

        content = tk.Frame(panel, bg=self.PANEL_BG)
        content.pack(fill="both", expand=True, padx=16, pady=16)

        header = tk.Frame(content, bg=self.PANEL_BG)
        header.pack(fill="x", pady=(0, 12))
        tk.Label(
            header,
            text="和桌宠对话",
            bg=self.PANEL_BG,
            fg=self.TEXT_FG,
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w")
        tk.Label(
            header,
            text="半透明的玻璃幕布式聊天面板",
            bg=self.PANEL_BG,
            fg=self.MUTED_FG,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(2, 0))

        history_shell = tk.Frame(
            content,
            bg=self.HISTORY_BG,
            bd=0,
            highlightthickness=1,
            highlightbackground="#344761",
            highlightcolor="#344761",
        )
        history_shell.pack(fill="both", expand=True)

        self.history = ScrolledText(
            history_shell,
            wrap="word",
            height=24,
            bg=self.HISTORY_BG,
            fg=self.TEXT_FG,
            insertbackground=self.TEXT_FG,
            selectbackground="#27425f",
            selectforeground=self.TEXT_FG,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            padx=14,
            pady=12,
            font=("Segoe UI", 10),
        )
        self.history.pack(fill="both", expand=True)
        self.history.configure(state="disabled")
        self.history.tag_configure("speaker", foreground=self.ACCENT_FG, font=("Segoe UI", 10, "bold"))
        self.history.tag_configure("content", foreground=self.TEXT_FG, lmargin1=6, lmargin2=6)
        self.history.tag_configure("system", foreground=self.MUTED_FG)

        input_area = tk.Frame(content, bg=self.PANEL_BG)
        input_area.pack(fill="x", pady=(14, 0))
        input_area.grid_columnconfigure(0, weight=1)

        input_shell = tk.Frame(
            input_area,
            bg=self.ENTRY_BG,
            bd=0,
            highlightthickness=1,
            highlightbackground="#344761",
            highlightcolor="#344761",
        )
        input_shell.grid(row=0, column=0, sticky="ew")

        self.input_var = tk.StringVar(value="")
        self.input_entry = tk.Entry(
            input_shell,
            textvariable=self.input_var,
            bg=self.ENTRY_BG,
            fg=self.TEXT_FG,
            insertbackground=self.TEXT_FG,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=("Segoe UI", 10),
        )
        self.input_entry.pack(side="left", fill="x", expand=True, padx=12, pady=10)
        self.input_entry.bind("<Return>", self._on_send)

        self.send_button = tk.Button(
            input_area,
            text="发送",
            command=self._on_send,
            bg=self.BUTTON_BG,
            fg=self.BUTTON_FG,
            activebackground=self.BUTTON_ACTIVE_BG,
            activeforeground=self.BUTTON_FG,
            relief="flat",
            bd=0,
            padx=18,
            pady=10,
            font=("Segoe UI", 10, "bold"),
            cursor="hand2",
        )
        self.send_button.grid(row=0, column=1, sticky="e", padx=(10, 0))

        footer = tk.Frame(content, bg=self.PANEL_BG)
        footer.pack(fill="x", pady=(12, 0))
        tk.Button(
            footer,
            text="清空",
            command=self._clear_history,
            bg="#1a2537",
            fg=self.TEXT_FG,
            activebackground="#223149",
            activeforeground=self.TEXT_FG,
            relief="flat",
            bd=0,
            padx=16,
            pady=7,
            font=("Segoe UI", 9),
            cursor="hand2",
        ).pack(side="left")
        tk.Button(
            footer,
            text="关闭",
            command=self.destroy,
            bg="#1a2537",
            fg=self.TEXT_FG,
            activebackground="#223149",
            activeforeground=self.TEXT_FG,
            relief="flat",
            bd=0,
            padx=16,
            pady=7,
            font=("Segoe UI", 9),
            cursor="hand2",
        ).pack(side="right")

        self._append_message("系统", "请输入内容开始对话。")
        self.input_entry.focus_set()

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.send_button.configure(state=state)
        self.input_entry.configure(state=state)

    def _append_message(self, speaker: str, content: str) -> None:
        self.history.configure(state="normal")
        if speaker == "系统":
            self.history.insert("end", f"{speaker}\n", ("system",))
            self.history.insert("end", f"{content}\n\n", ("system",))
        else:
            self.history.insert("end", f"{speaker}\n", ("speaker",))
            self.history.insert("end", f"{content}\n\n", ("content",))
        self.history.see("end")
        self.history.configure(state="disabled")

    def _begin_streamed_message(self, speaker: str) -> None:
        self.history.configure(state="normal")
        self.history.insert("end", f"{speaker}\n", ("speaker",))
        self.history.configure(state="disabled")
        self._streaming_reply_active = True

    def _append_stream_chunk(self, chunk: str) -> None:
        if not chunk:
            return
        self.history.configure(state="normal")
        self.history.insert("end", chunk, ("content",))
        self.history.see("end")
        self.history.configure(state="disabled")

    def _append_stream_tool_event(self, tool_name: str, tool_result: dict[str, object]) -> None:
        self.history.configure(state="normal")
        self.history.insert("end", f"\n[工具] {tool_name}\n", ("system",))
        self.history.insert("end", f"{tool_result}\n", ("system",))
        self.history.see("end")
        self.history.configure(state="disabled")

    def _finish_streamed_message(self) -> None:
        if not self._streaming_reply_active:
            return
        self.history.configure(state="normal")
        self.history.insert("end", "\n\n", ("content",))
        self.history.see("end")
        self.history.configure(state="disabled")
        self._streaming_reply_active = False

    def _clear_history(self) -> None:
        if self._busy:
            return
        self.history.configure(state="normal")
        self.history.delete("1.0", "end")
        self.history.configure(state="disabled")

    def _on_send(self, event: tk.Event | None = None) -> str | None:
        if self._busy:
            return "break"
        user_text = self.input_var.get().strip()
        if not user_text:
            return "break"

        self.input_var.set("")
        self._append_message("你", user_text)
        self._set_busy(True)
        if self.on_pet_action is not None:
            self.on_pet_action("think")
        self._begin_streamed_message("桌宠")
        self._append_stream_chunk("AI 正在输出…\n")

        threading.Thread(target=self._worker, args=(user_text,), daemon=True).start()
        return "break"

    def _worker(self, user_text: str) -> None:
        try:
            reply_parts: list[str] = []

            def on_chunk(chunk: str) -> None:
                reply_parts.append(chunk)
                self.after(0, lambda chunk=chunk: self._append_stream_chunk(chunk))

            def on_tool_event(tool_name: str, tool_result: dict[str, object]) -> None:
                self.after(0, lambda: self._append_stream_tool_event(tool_name, tool_result))

            result = self.agent.ask_stream(user_text, on_chunk=on_chunk, on_tool_event=on_tool_event)
            reply = "".join(reply_parts).strip() or result.reply
            streamed = bool(reply_parts)
        except Exception as exc:  # noqa: BLE001
            reply = f"请求失败: {exc}"
            streamed = False

        self.after(0, lambda: self._complete_turn(reply, streamed))

    def _complete_turn(self, reply: str, streamed: bool) -> None:
        self._finish_streamed_message()
        if not streamed and reply:
            self._append_message("桌宠", reply)
        if self.on_pet_action is not None:
            self.on_pet_action("answer")
            self.after(1200, lambda: self.on_pet_action("idle"))
        self._set_busy(False)
        self.input_entry.focus_set()
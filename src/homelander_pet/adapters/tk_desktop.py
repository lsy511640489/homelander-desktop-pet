from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk

from fractions import Fraction

from PIL import Image, ImageOps, ImageTk

from homelander_pet.agent.orchestrator import HomelanderAgent
from homelander_pet.adapters.stock_tracker import StockTrendSnapshot, StockTrendTracker
from homelander_pet.chat.window import ChatWindow
from homelander_pet.core.runtime import PetRuntime


class AlphaVideoReader:
    def __init__(self, path: Path, loop: bool) -> None:
        self.path = path
        self.loop = loop
        self.width, self.height, self.fps = self._probe_video(path)
        self._frame_size = self.width * self.height * 4
        self._process: subprocess.Popen[bytes] | None = None
        self._start_process()

    def _probe_video(self, path: Path) -> tuple[int, int, float]:
        command = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,r_frame_rate",
            "-of",
            "json",
            str(path),
        ]
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
        payload = json.loads(completed.stdout)
        stream = payload["streams"][0]
        width = int(stream["width"])
        height = int(stream["height"])
        fps = float(Fraction(stream.get("r_frame_rate", "0/1")))
        return width, height, fps

    def _start_process(self) -> None:
        command = [
            "ffmpeg",
            "-loglevel",
            "error",
            "-i",
            str(self.path),
            "-an",
            "-sn",
            "-dn",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgba",
            "pipe:1",
        ]
        self._process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def close(self) -> None:
        if self._process is None:
            return
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self._process.kill()
        self._process = None

    def _read_exact(self, size: int) -> bytes | None:
        if self._process is None or self._process.stdout is None:
            return None

        chunks = bytearray()
        while len(chunks) < size:
            chunk = self._process.stdout.read(size - len(chunks))
            if not chunk:
                return None if not chunks else bytes(chunks)
            chunks.extend(chunk)
        return bytes(chunks)

    def read_frame(self) -> Image.Image | None:
        data = self._read_exact(self._frame_size)
        if data is None or len(data) < self._frame_size:
            if not self.loop:
                return None
            self.close()
            self._start_process()
            data = self._read_exact(self._frame_size)
            if data is None or len(data) < self._frame_size:
                return None

        return Image.frombytes("RGBA", (self.width, self.height), data)


class DesktopPetWindow(tk.Tk):
    BASE_CANVAS_SIZE = (192, 300)
    DISPLAY_SCALE = 0.4
    TRANSPARENT_COLOR = "#E51B0D"
    TRANSPARENT_COLOR_UP = "#e74c3c"
    TRANSPARENT_COLOR_DOWN = "#ef0eb3"
    INLINE_CHAT_INPUT_HEIGHT = 44
    INLINE_CHAT_REPLY_HEIGHT = 96
    INLINE_CHAT_WIDTH = 320
    INLINE_CHAT_HEIGHT = 300
    INLINE_CHAT_MIN_WIDTH = 280
    INLINE_CHAT_MIN_HEIGHT = 150
    INLINE_CHAT_BG = "#427de4"                 # 全局背景（若需透传，可保持透明，这里为极浅灰）
    INLINE_CHAT_PANEL_BG = "#aed0ed"           # 主面板背景：纯白，干净利落
    INLINE_CHAT_PANEL_EDGE = "#dbccc9"         # 右下拉伸按钮：浅岩灰
    INLINE_CHAT_PANEL_EDGE_FOCUS = "#f1e7e6"   # 聚焦边框：中灰，低调反馈
    INLINE_CHAT_INNER_BG = "#fafafc"           # 回复区域背景：微暖白
    INLINE_CHAT_ENTRY_BG = "#ffffff"           # 输入框背景：纯白
    INLINE_CHAT_TEXT_FG = "#494746"            # 主要文字：深炭灰
    INLINE_CHAT_MUTED_FG = "#91b5f0"           # 辅助文字：柔和灰
    INLINE_CHAT_ACCENT_FG = "#4480f7"          # 状态/高亮文字：淡紫色（仅做极轻微点缀）
    INLINE_CHAT_BUTTON_BG = "#36a2ea"          # 按钮背景：浅灰
    INLINE_CHAT_BUTTON_ACTIVE_BG = "#c7eaec"   # 按钮按下背景：稍深灰
    INLINE_CHAT_BUTTON_FG = "#2c3e50"          # 按钮文字：深海暗蓝灰
    INLINE_CHAT_PLACEHOLDER = "呼叫阿祖"
    CANVAS_SIZE = (
        max(1, round(BASE_CANVAS_SIZE[0] * DISPLAY_SCALE)),
        max(1, round(BASE_CANVAS_SIZE[1] * DISPLAY_SCALE)),
    )
    DRAG_THRESHOLD = 4

    def __init__(self, runtime: PetRuntime, conversation_agent: HomelanderAgent | None = None) -> None:
        super().__init__()
        self.runtime = runtime
        self.conversation_agent = conversation_agent
        self._chat_window: ChatWindow | None = None
        self._transparent_color = self.TRANSPARENT_COLOR
        self._transparent_widgets: list[tk.Widget] = []
        self._stock_tracker = StockTrendTracker.from_environment()
        self._stock_refresh_job: str | None = None
        self._stock_poll_job: str | None = None
        self._stock_refresh_running = False
        self._stock_refresh_results: queue.Queue[tuple[StockTrendSnapshot | None, Exception | None, bool]] = queue.Queue()
        self.title(runtime.profile.display_name)
        self.geometry(f"{self.CANVAS_SIZE[0]}x{self.CANVAS_SIZE[1]}+120+120")
        self.minsize(*self.CANVAS_SIZE)
        self.attributes("-topmost", True)
        self.overrideredirect(True)
        self.resizable(False, False)

        self._video_reader: AlphaVideoReader | None = None
        self._video_delay_ms = 33
        self._current_frame_image: ImageTk.PhotoImage | None = None
        self._drag_origin: tuple[int, int] | None = None
        self._window_origin: tuple[int, int] | None = None
        self._dragging = False
        self._left_press_active = False
        self._revert_job: str | None = None
        self._tick_job: str | None = None
        self._drag_offset: tuple[int, int] | None = None
        self._inline_chat_visible = False
        self._inline_chat_busy = False
        self._inline_chat_streaming = False
        self._inline_chat_size: tuple[int, int] = (self.INLINE_CHAT_WIDTH, self.INLINE_CHAT_HEIGHT)
        self._inline_chat_resize_anchor: tuple[int, int] | None = None
        self._inline_chat_resize_start_size: tuple[int, int] | None = None
        self._debug_mode = os.environ.get("HOMELANDER_PET_DEBUG_UI") == "1"
        self.log_text: tk.Text | None = None
        self._inline_chat_frame: tk.Frame | None = None
        self._inline_chat_shell: tk.Frame | None = None
        self._inline_chat_panel: tk.Frame | None = None
        self._inline_chat_resize_grip: tk.Frame | None = None
        self._inline_chat_status_var = tk.StringVar(value="对话")
        self._inline_chat_input_var = tk.StringVar(value="")
        self._inline_chat_status_label: tk.Label | None = None
        self._inline_chat_reply_text: tk.Text | None = None
        self._inline_chat_entry: tk.Entry | None = None
        self._inline_chat_send_button: tk.Button | None = None

        self._build_ui()
        self._refresh_state()
        self.activate_action(self.runtime.current_action)
        self._refresh_stock_trend(initial=True)
        self._tick_job = self.after(self._video_delay_ms, self._tick_video)
        self.after_idle(self._ensure_focus)

    def _build_ui(self) -> None:
        self.configure(background=self._transparent_color)
        if sys.platform.startswith("win"):
            try:
                self.attributes("-transparentcolor", self._transparent_color)
            except tk.TclError:
                pass

        outer = tk.Frame(self, background=self._transparent_color)
        outer.pack(fill="both", expand=True)
        self._transparent_widgets.append(outer)

        body = tk.Frame(outer, background=self._transparent_color)
        body.pack(fill="both", expand=True)
        self._transparent_widgets.append(body)

        self.video_label = tk.Label(body, background=self._transparent_color, width=self.CANVAS_SIZE[0], height=self.CANVAS_SIZE[1], bd=0, highlightthickness=0)
        self.video_label.pack(fill="both", expand=True)
        self._transparent_widgets.append(self.video_label)

        self._inline_chat_frame = tk.Frame(body, background=self._transparent_color, height=self.INLINE_CHAT_INPUT_HEIGHT + self.INLINE_CHAT_REPLY_HEIGHT)
        self._inline_chat_frame.pack(side="bottom", fill="x", padx=4, pady=(0, 4))
        self._inline_chat_frame.pack_propagate(False)
        self._transparent_widgets.append(self._inline_chat_frame)

        self._inline_chat_shell = tk.Frame(self._inline_chat_frame, bg=self.INLINE_CHAT_BG, bd=0, highlightthickness=0)
        self._inline_chat_shell.pack(fill="both", expand=True)

        self._inline_chat_panel = tk.Frame(
            self._inline_chat_shell,
            bg=self.INLINE_CHAT_PANEL_BG,
            bd=0,
            highlightthickness=1,
            highlightbackground=self.INLINE_CHAT_PANEL_EDGE,
            highlightcolor=self.INLINE_CHAT_PANEL_EDGE,
        )
        self._inline_chat_panel.pack(fill="both", expand=True, padx=2, pady=2)

        self._inline_chat_panel.grid_columnconfigure(1, weight=1)
        self._inline_chat_panel.grid_columnconfigure(0, weight=0)
        self._inline_chat_panel.grid_columnconfigure(2, weight=0)
        self._inline_chat_panel.grid_rowconfigure(2, weight=1, minsize=42)
        self._inline_chat_panel.grid_rowconfigure(3, minsize=10)

        top_bar = tk.Frame(self._inline_chat_panel, bg=self.INLINE_CHAT_PANEL_BG)
        top_bar.grid(row=0, column=0, columnspan=3, sticky="ew", padx=12, pady=(10, 6))
        self._inline_chat_status_label = tk.Label(top_bar, textvariable=self._inline_chat_status_var, bg=self.INLINE_CHAT_PANEL_BG, fg=self.INLINE_CHAT_ACCENT_FG, width=6, anchor="w", font=("Segoe UI", 10, "bold"))
        self._inline_chat_status_label.pack(side="left")

        input_shell = tk.Frame(self._inline_chat_panel, bg=self.INLINE_CHAT_ENTRY_BG, bd=0, highlightthickness=1, highlightbackground="#364a63", highlightcolor="#364a63")
        input_shell.grid(row=1, column=0, columnspan=2, sticky="ew", padx=(12, 6), pady=(0, 8))
        input_shell.grid_columnconfigure(0, weight=1)

        self._inline_chat_entry = tk.Entry(
            input_shell,
            textvariable=self._inline_chat_input_var,
            bg=self.INLINE_CHAT_ENTRY_BG,
            fg=self.INLINE_CHAT_TEXT_FG,
            insertbackground=self.INLINE_CHAT_TEXT_FG,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=("Segoe UI", 10),
        )
        self._inline_chat_entry.grid(row=0, column=0, sticky="ew", padx=12, pady=8)
        self._inline_chat_entry.bind("<Return>", self._submit_inline_chat)
        self._inline_chat_entry.bind("<Escape>", self._hide_inline_chat)

        self._inline_chat_send_button = tk.Button(
            self._inline_chat_panel,
            text="呼叫阿祖",
            command=self._submit_inline_chat,
            bg=self.INLINE_CHAT_BUTTON_BG,
            fg=self.INLINE_CHAT_BUTTON_FG,
            activebackground=self.INLINE_CHAT_BUTTON_ACTIVE_BG,
            activeforeground=self.INLINE_CHAT_BUTTON_FG,
            relief="flat",
            bd=0,
            padx=16,
            pady=8,
            font=("Segoe UI", 10, "bold"),
            cursor="hand2",
        )
        self._inline_chat_send_button.grid(row=1, column=2, sticky="e", padx=(0, 12), pady=(0, 8))

        reply_shell = tk.Frame(self._inline_chat_panel, bg=self.INLINE_CHAT_INNER_BG, bd=0, highlightthickness=0)
        reply_shell.grid(row=2, column=0, columnspan=3, sticky="nsew", padx=12, pady=(0, 0))
        reply_shell.grid_rowconfigure(0, weight=1)
        reply_shell.grid_columnconfigure(0, weight=1)

        self._inline_chat_reply_text = tk.Text(
            reply_shell,
            wrap="word",
            height=6,
            bg=self.INLINE_CHAT_INNER_BG,
            fg=self.INLINE_CHAT_TEXT_FG,
            insertbackground=self.INLINE_CHAT_TEXT_FG,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            padx=12,
            pady=6,
            font=("Segoe UI", 10),
        )
        self._inline_chat_reply_text.grid(row=0, column=0, sticky="nsew")
        reply_scrollbar = tk.Scrollbar(reply_shell, orient="vertical", command=self._inline_chat_reply_text.yview)
        reply_scrollbar.grid(row=0, column=1, sticky="ns")
        self._inline_chat_reply_text.configure(yscrollcommand=reply_scrollbar.set)

        self._inline_chat_resize_grip = tk.Frame(
            self._inline_chat_panel,
            bg=self.INLINE_CHAT_PANEL_EDGE,
            width=14,
            height=14,
            cursor="size_nw_se",
            bd=0,
            highlightthickness=0,
        )
        self._inline_chat_resize_grip.place(relx=1.0, rely=1.0, x=-6, y=-1, anchor="se")
        self._inline_chat_resize_grip.bind("<ButtonPress-1>", self._start_inline_chat_resize)
        self._inline_chat_resize_grip.bind("<B1-Motion>", self._do_inline_chat_resize)
        self._inline_chat_resize_grip.bind("<ButtonRelease-1>", self._stop_inline_chat_resize)

        self._inline_chat_frame.pack_forget()
        self._set_inline_chat_reply_text(self.INLINE_CHAT_PLACEHOLDER)
        self._apply_inline_chat_geometry(*self._inline_chat_size)

        if self._debug_mode:
            container = ttk.Frame(outer, padding=4)
            container.pack(fill="x", expand=False)

            ttk.Label(container, text="桌宠最小可用运行时", foreground="#bbbbbb").pack(anchor="w", pady=(2, 6))

            self.state_var = tk.StringVar(value="")
            self.media_var = tk.StringVar(value="")
            self.query_var = tk.StringVar(value="")

            ttk.Label(container, textvariable=self.state_var, wraplength=400).pack(anchor="w", pady=(0, 4))
            ttk.Label(container, textvariable=self.media_var, wraplength=400).pack(anchor="w", pady=(0, 6))

            actions_frame = ttk.LabelFrame(container, text="动作")
            actions_frame.pack(fill="x", pady=(0, 6))

            for action in self.runtime.actions.values():
                button = ttk.Button(actions_frame, text=action.label, command=lambda action_id=action.id: self.activate_action(action_id))
                button.pack(fill="x", padx=4, pady=2)

            query_frame = ttk.LabelFrame(container, text="问答占位")
            query_frame.pack(fill="x", pady=(0, 6))
            entry = ttk.Entry(query_frame, textvariable=self.query_var)
            entry.pack(fill="x", padx=4, pady=(4, 4))
            ttk.Button(query_frame, text="发送到 LLM 占位", command=self._send_query_placeholder).pack(fill="x", padx=4, pady=(0, 4))

            ttk.Label(container, text="运行日志").pack(anchor="w")
            self.log_text = tk.Text(container, height=6, wrap="word")
            self.log_text.pack(fill="both", expand=True, pady=(4, 4))
            self.log_text.configure(state="disabled")

            footer = tk.Frame(container, bg=self.INLINE_CHAT_BG)
            footer.pack(fill="x")
            if self.conversation_agent is not None:
                tk.Button(
                    footer,
                    text="对话",
                    command=self._open_chat_window,
                    bg=self.INLINE_CHAT_BUTTON_BG,
                    fg=self.INLINE_CHAT_BUTTON_FG,
                    activebackground=self.INLINE_CHAT_BUTTON_ACTIVE_BG,
                    activeforeground=self.INLINE_CHAT_BUTTON_FG,
                    relief="flat",
                    bd=0,
                    padx=16,
                    pady=7,
                    font=("Segoe UI", 9, "bold"),
                    cursor="hand2",
                ).pack(side="left")
            tk.Button(
                footer,
                text="重置待机",
                command=lambda: self.activate_action(self.runtime.profile.avatar.default_action),
                bg="#1a2537",
                fg=self.INLINE_CHAT_TEXT_FG,
                activebackground="#223149",
                activeforeground=self.INLINE_CHAT_TEXT_FG,
                relief="flat",
                bd=0,
                padx=16,
                pady=7,
                font=("Segoe UI", 9),
                cursor="hand2",
            ).pack(side="left", padx=(8, 0))
            tk.Button(
                footer,
                text="退出",
                command=self._request_exit,
                bg="#1a2537",
                fg=self.INLINE_CHAT_TEXT_FG,
                activebackground="#223149",
                activeforeground=self.INLINE_CHAT_TEXT_FG,
                relief="flat",
                bd=0,
                padx=16,
                pady=7,
                font=("Segoe UI", 9),
                cursor="hand2",
            ).pack(side="right")

        elif self.conversation_agent is not None:
            footer = tk.Frame(outer, bg=self._transparent_color)
            footer.pack(fill="x", expand=False)
            self._transparent_widgets.append(footer)
            tk.Button(
                footer,
                text="对话",
                command=self._open_chat_window,
                bg=self.INLINE_CHAT_BUTTON_BG,
                fg=self.INLINE_CHAT_BUTTON_FG,
                activebackground=self.INLINE_CHAT_BUTTON_ACTIVE_BG,
                activeforeground=self.INLINE_CHAT_BUTTON_FG,
                relief="flat",
                bd=0,
                padx=16,
                pady=7,
                font=("Segoe UI", 9, "bold"),
                cursor="hand2",
            ).pack(side="left")
            tk.Button(
                footer,
                text="退出",
                command=self._request_exit,
                bg="#1a2537",
                fg=self.INLINE_CHAT_TEXT_FG,
                activebackground="#223149",
                activeforeground=self.INLINE_CHAT_TEXT_FG,
                relief="flat",
                bd=0,
                padx=16,
                pady=7,
                font=("Segoe UI", 9),
                cursor="hand2",
            ).pack(side="right")

        self.bind("<Escape>", self._on_exit_hotkey)
        self.bind("<Control-l>", self._on_exit_hotkey)
        self.bind_all("<Control-L>", self._on_exit_hotkey)
        self.bind_all("<Control-k>", self._toggle_inline_chat_hotkey)
        self.bind_all("<Control-K>", self._toggle_inline_chat_hotkey)

        for widget in (self, outer, body, self.video_label):
            widget.bind("<ButtonPress-1>", self._start_primary_gesture)
            widget.bind("<B1-Motion>", self._move_primary_gesture)
            widget.bind("<ButtonRelease-1>", self._end_primary_gesture)
            widget.bind("<ButtonPress-3>", self._start_drag)
            widget.bind("<B3-Motion>", self._do_drag)
            widget.bind("<ButtonRelease-3>", self._stop_drag)

    def _append_log(self, message: str) -> None:
        if self.log_text is None:
            return
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _on_exit_hotkey(self, _event: tk.Event | None = None) -> None:
        self._request_exit()

    def _request_exit(self) -> None:
        if self._revert_job is not None:
            self.after_cancel(self._revert_job)
            self._revert_job = None
        if self._tick_job is not None:
            self.after_cancel(self._tick_job)
            self._tick_job = None
        if self._stock_refresh_job is not None:
            self.after_cancel(self._stock_refresh_job)
            self._stock_refresh_job = None
        if self._stock_poll_job is not None:
            self.after_cancel(self._stock_poll_job)
            self._stock_poll_job = None
        if self._video_reader is not None:
            self._video_reader.close()
            self._video_reader = None
        if self._chat_window is not None:
            self._chat_window.destroy()
            self._chat_window = None
        self.destroy()

    def _apply_transparent_color(self, color: str) -> None:
        if not color or color == self._transparent_color:
            return

        self._transparent_color = color
        try:
            self.configure(background=color)
        except tk.TclError:
            pass
        for widget in self._transparent_widgets:
            try:
                widget.configure(background=color)
            except tk.TclError:
                continue

        if sys.platform.startswith("win"):
            try:
                self.attributes("-transparentcolor", color)
            except tk.TclError:
                pass

    def _refresh_stock_trend(self, initial: bool = False) -> None:
        if self._stock_tracker is None or self._stock_refresh_running:
            return

        self._stock_refresh_running = True

        def worker() -> None:
            try:
                snapshot = self._stock_tracker.snapshot()
            except Exception as exc:  # noqa: BLE001
                self._stock_refresh_results.put((None, exc, initial))
                return

            self._stock_refresh_results.put((snapshot, None, initial))

        threading.Thread(target=worker, daemon=True).start()
        if self._stock_poll_job is None:
            self._stock_poll_job = self.after(100, self._poll_stock_refresh_results)

    def _poll_stock_refresh_results(self) -> None:
        self._stock_poll_job = None

        try:
            snapshot, error, initial = self._stock_refresh_results.get_nowait()
        except queue.Empty:
            if self._stock_refresh_running:
                self._stock_poll_job = self.after(100, self._poll_stock_refresh_results)
            return

        self._finish_stock_refresh(snapshot, error, initial)

        if self._stock_refresh_running:
            self._stock_poll_job = self.after(100, self._poll_stock_refresh_results)

    def _finish_stock_refresh(
        self,
        snapshot: StockTrendSnapshot | None,
        error: Exception | None,
        initial: bool,
    ) -> None:
        self._stock_refresh_running = False

        if snapshot is not None:
            self._apply_transparent_color(snapshot.color)
            if self._debug_mode:
                summary = f"股票趋势: {snapshot.direction} {snapshot.net_change:+.2f} ({snapshot.net_change_percent:+.2f}%)"
                self._append_log(summary)
        elif error is not None and self._debug_mode and initial:
            self._append_log(f"股票趋势未启用或拉取失败: {error}")

        self._schedule_stock_refresh()

    def _schedule_stock_refresh(self) -> None:
        if self._stock_tracker is None:
            return
        if self._stock_refresh_job is not None:
            self.after_cancel(self._stock_refresh_job)
            self._stock_refresh_job = None
        delay_ms = max(1000, int(self._stock_tracker.refresh_seconds * 1000))
        self._stock_refresh_job = self.after(delay_ms, self._refresh_stock_trend)

    def _toggle_inline_chat_hotkey(self, _event: tk.Event | None = None) -> str | None:
        if self.conversation_agent is None:
            return None
        if self._inline_chat_visible:
            self._hide_inline_chat()
        else:
            self._show_inline_chat()
        return "break"

    def _show_inline_chat(self, _event: tk.Event | None = None) -> None:
        if self._inline_chat_visible or self._inline_chat_frame is None:
            return
        self._inline_chat_visible = True
        self._inline_chat_frame.pack(side="bottom", fill="x", padx=4, pady=(0, 4))
        self._resize_window_for_inline_chat(True)
        if self._inline_chat_reply_text is not None:
            current_text = self._inline_chat_reply_text.get("1.0", "end").strip()
            if not current_text:
                self._set_inline_chat_reply_text(self.INLINE_CHAT_PLACEHOLDER)
        if self._inline_chat_entry is not None:
            self.after_idle(self._focus_inline_chat_entry)

    def _hide_inline_chat(self, _event: tk.Event | None = None) -> str | None:
        if not self._inline_chat_visible or self._inline_chat_frame is None:
            return None
        self._inline_chat_visible = False
        self._inline_chat_frame.pack_forget()
        self._resize_window_for_inline_chat(False)
        return "break"

    def _resize_window_for_inline_chat(self, visible: bool) -> None:
        if visible:
            width, height = self._inline_chat_size
        else:
            width, height = self.CANVAS_SIZE[0], self.CANVAS_SIZE[1]
        self.geometry(f"{width}x{height}+{self.winfo_x()}+{self.winfo_y()}")
        if visible:
            self._apply_inline_chat_geometry(width, height)

    def _apply_inline_chat_geometry(self, width: int, height: int) -> None:
        if self._inline_chat_reply_text is None:
            return
        if self._inline_chat_panel is not None:
            self._inline_chat_panel.configure(height=height)
        if self._inline_chat_frame is not None:
            self._inline_chat_frame.configure(height=height)

    def _start_inline_chat_resize(self, event: tk.Event) -> None:
        if self._inline_chat_frame is None:
            return
        self._inline_chat_resize_anchor = (event.x_root, event.y_root)
        self._inline_chat_resize_start_size = self._inline_chat_size

    def _do_inline_chat_resize(self, event: tk.Event) -> None:
        if self._inline_chat_resize_anchor is None or self._inline_chat_resize_start_size is None:
            return
        start_x, start_y = self._inline_chat_resize_anchor
        start_width, start_height = self._inline_chat_resize_start_size
        delta_x = event.x_root - start_x
        delta_y = event.y_root - start_y
        new_width = max(self.INLINE_CHAT_MIN_WIDTH, start_width + delta_x)
        new_height = max(self.INLINE_CHAT_MIN_HEIGHT, start_height + delta_y)
        self._inline_chat_size = (new_width, new_height)
        self._resize_window_for_inline_chat(True)

    def _stop_inline_chat_resize(self, _event: tk.Event | None = None) -> None:
        self._inline_chat_resize_anchor = None
        self._inline_chat_resize_start_size = None

    def _set_inline_chat_busy(self, busy: bool) -> None:
        self._inline_chat_busy = busy
        state = "disabled" if busy else "normal"
        if self._inline_chat_entry is not None:
            self._inline_chat_entry.configure(state=state)
        if self._inline_chat_send_button is not None:
            self._inline_chat_send_button.configure(state=state)

    def _compact_inline_reply(self, text: str, limit: int = 24) -> str:
        stripped = " ".join(text.split())
        if len(stripped) <= limit:
            return stripped
        return stripped[: max(0, limit - 1)] + "…"

    def _set_inline_chat_reply_text(self, text: str) -> None:
        if self._inline_chat_reply_text is None:
            return
        self._inline_chat_reply_text.configure(state="normal")
        self._inline_chat_reply_text.delete("1.0", "end")
        self._inline_chat_reply_text.insert("end", text)
        self._inline_chat_reply_text.see("end")
        self._inline_chat_reply_text.configure(state="disabled")

    def _append_inline_chat_reply_text(self, text: str) -> None:
        if self._inline_chat_reply_text is None or not text:
            return
        self._inline_chat_reply_text.configure(state="normal")
        self._inline_chat_reply_text.insert("end", text)
        self._inline_chat_reply_text.see("end")
        self._inline_chat_reply_text.configure(state="disabled")

    def _submit_inline_chat(self, event: tk.Event | None = None) -> str | None:
        if self.conversation_agent is None or self._inline_chat_busy:
            return "break"
        user_text = self._inline_chat_input_var.get().strip()
        if not user_text:
            return "break"

        self._inline_chat_input_var.set("")
        self._set_inline_chat_busy(True)
        self._inline_chat_status_var.set("AI")
        self._set_inline_chat_reply_text("AI 正在输出…\n")
        self._inline_chat_streaming = True
        self.activate_action("think")
        threading.Thread(target=self._run_inline_chat, args=(user_text,), daemon=True).start()
        return "break"

    def _run_inline_chat(self, user_text: str) -> None:
        try:
            reply_parts: list[str] = []

            def on_chunk(chunk: str) -> None:
                reply_parts.append(chunk)
                self.after(0, lambda chunk=chunk: self._append_inline_chat_reply_text(chunk))

            def on_tool_event(tool_name: str, tool_result: dict[str, object]) -> None:
                summary = f"\n[工具] {tool_name}\n{tool_result}\n"
                self.after(0, lambda summary=summary: self._append_inline_chat_reply_text(summary))

            result = self.conversation_agent.ask_stream(user_text, on_chunk=on_chunk, on_tool_event=on_tool_event)
            reply = "".join(reply_parts).strip() or result.reply
            streamed = bool(reply_parts)
        except Exception as exc:  # noqa: BLE001
            reply = f"失败: {exc}"
            streamed = False

        self.after(0, lambda: self._finish_inline_chat(reply, streamed))

    def _finish_inline_chat(self, reply: str, streamed: bool) -> None:
        self._inline_chat_streaming = False
        self._inline_chat_status_var.set("月牙天冲")
        if not streamed:
            if not reply:
                reply = "我暂时没有可返回的内容。"
            self._set_inline_chat_reply_text(reply)
        elif not reply:
            reply = "我暂时没有可返回的内容。"
        self.activate_action("answer")
        self.after(1200, lambda: self.activate_action(self.runtime.profile.avatar.default_action))
        self._set_inline_chat_busy(False)
        if self._inline_chat_entry is not None:
            self._focus_inline_chat_entry()

    def _focus_inline_chat_entry(self) -> None:
        if self._inline_chat_entry is None:
            return
        self._inline_chat_entry.focus_force()
        self._inline_chat_entry.icursor("end")

    def _open_chat_window(self) -> None:
        if self.conversation_agent is None:
            return
        if self._chat_window is not None and self._chat_window.winfo_exists():
            self._chat_window.lift()
            self._chat_window.focus_force()
            return
        self._chat_window = ChatWindow(self, self.conversation_agent, on_pet_action=self.activate_action)

    def _ensure_focus(self) -> None:
        try:
            self.lift()
            self.focus_force()
        except tk.TclError:
            pass

    def _refresh_state(self) -> None:
        if self._debug_mode:
            self.state_var.set(self.runtime.describe_current_state())
            self.media_var.set(f"资源: {self.runtime.current_media_path}")

    def activate_action(self, action_id: str) -> None:
        if self._revert_job is not None:
            self.after_cancel(self._revert_job)
            self._revert_job = None
        if action_id == self.runtime.current_action and action_id != "click" and self._video_reader is not None:
            return
        self.runtime.set_action(action_id)
        self._refresh_state()
        self._append_log(f"切换动作: {action_id}")
        self._start_media(self.runtime.current_media_path, self.runtime.actions[action_id].loop)

    def _start_primary_gesture(self, event: tk.Event) -> None:
        self._left_press_active = True
        self._dragging = False
        self._drag_origin = (event.x_root, event.y_root)
        self._window_origin = (self.winfo_x(), self.winfo_y())

    def _move_primary_gesture(self, event: tk.Event) -> None:
        if not self._left_press_active or self._drag_origin is None or self._window_origin is None:
            return

        start_x, start_y = self._drag_origin
        delta_x = event.x_root - start_x
        delta_y = event.y_root - start_y

        if not self._dragging:
            if abs(delta_x) < self.DRAG_THRESHOLD and abs(delta_y) < self.DRAG_THRESHOLD:
                return
            self._dragging = True
            self.activate_action("drag_start")

        origin_x, origin_y = self._window_origin
        self.geometry(f"+{origin_x + delta_x}+{origin_y + delta_y}")
        self.activate_action("drag_move")

    def _end_primary_gesture(self, _event: tk.Event) -> None:
        if self._left_press_active and not self._dragging:
            self._trigger_click()
        elif self._dragging:
            self.activate_action(self.runtime.profile.avatar.default_action)
        self._left_press_active = False
        self._dragging = False
        self._drag_origin = None
        self._window_origin = None

    def _trigger_click(self) -> None:
        if self.runtime.current_action == "click":
            return
        self.activate_action("click")
        self._revert_job = self.after(320, self._revert_to_idle)

    def _revert_to_idle(self) -> None:
        self._revert_job = None
        self.activate_action(self.runtime.profile.avatar.default_action)

    def _start_drag(self, event: tk.Event) -> None:
        self._drag_offset = (event.x_root, event.y_root)
        self._dragging = True

    def _do_drag(self, event: tk.Event) -> None:
        if not self._dragging or self._drag_offset is None:
            return
        start_x, start_y = self._drag_offset
        self.geometry(f"+{event.x_root - start_x + self.winfo_x()}+{event.y_root - start_y + self.winfo_y()}")

    def _stop_drag(self, _event: tk.Event) -> None:
        self._drag_offset = None
        self._dragging = False

    def _start_media(self, media_path: str, loop: bool) -> None:
        if self._video_reader is not None:
            self._video_reader.close()
            self._video_reader = None

        path = Path(media_path)
        if not path.is_absolute():
            path = self.runtime.profile.asset_root.parent.parent / path

        if not path.exists():
            self.video_label.configure(text=f"缺少媒体文件\n{path}", image="")
            self._append_log(f"媒体文件不存在: {path}")
            return

        try:
            self._video_reader = AlphaVideoReader(path, loop=loop)
        except (OSError, subprocess.SubprocessError, KeyError, IndexError, ValueError, json.JSONDecodeError) as exc:
            self.video_label.configure(text=f"无法打开媒体\n{path}", image="")
            self._append_log(f"无法打开媒体: {path} ({exc})")
            return

        fps = self._video_reader.fps
        self._video_delay_ms = int(1000 / fps) if fps and fps > 0 else 33
        self._append_log(f"开始播放: {path}")

    def _tick_video(self) -> None:
        if self._video_reader is not None:
            frame = self._video_reader.read_frame()
            if frame is None:
                if not self._video_reader.loop:
                    self._append_log("媒体播放结束")
                    self._video_reader.close()
                    self._video_reader = None
                else:
                    self._append_log("媒体重新开始播放")
            else:
                frame = ImageOps.fit(frame, self.CANVAS_SIZE, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
                self._current_frame_image = ImageTk.PhotoImage(image=frame)
                self.video_label.configure(image=self._current_frame_image, text="")

            self._tick_job = self.after(self._video_delay_ms, self._tick_video)

    def _send_query_placeholder(self) -> None:
        query = self.query_var.get().strip()
        if not query:
            self._append_log("问答输入为空")
            return
        self._append_log(f"LLM 占位请求: {query}")

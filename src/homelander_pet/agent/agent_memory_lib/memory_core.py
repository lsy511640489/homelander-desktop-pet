from . import memory_storage as storage
import os

def sequential_sample_compress(text: str, compress_level: int) -> str:
    if compress_level <= 0:
        return text.strip()
    if not text.strip():
        return ""

    min_keep_ratio = 0.15
    keep_ratio = 1.0 - (compress_level / 100) * (1.0 - min_keep_ratio)
    keep_len = int(len(text) * keep_ratio)

    if keep_len >= len(text):
        return text.strip()

    step = len(text) / keep_len
    sampled_chars = []
    for i in range(keep_len):
        idx = int(i * step)
        sampled_chars.append(text[idx])

    return "".join(sampled_chars) + "\n【已按等级顺序压缩】"


class CompressedAgentMemory:
    def __init__(
        self,
        short_term_max_round: int = 5,
        daily_compress_level: int = 30
    ):
        storage.init_storage()
        self.short_term_max_round = short_term_max_round
        self.daily_compress_level = max(0, min(100, daily_compress_level))

        # 每日加载模式
        self.load_all_daily = False      # 是否加载全部天数
        self.load_specify_days = []      # 指定加载哪几天，格式 ["2026-05-01","2026-05-03"]

    # ---------------- 永久设定 ----------------
    def set_permanent_content(self, md_content: str):
        storage.write_md(storage.PATH_PERMANENT, md_content)

    def get_permanent_content(self) -> str:
        return storage.read_md(storage.PATH_PERMANENT)

    # ---------------- 短期最近对话 ----------------
    def get_short_term_content(self) -> str:
        return storage.read_md(storage.PATH_SHORT_TERM)

    def _split_rounds(self, content: str):
        return [r.strip() for r in content.split("---") if r.strip()]

    def add_chat_round(self, user_msg: str, assistant_msg: str):
        # 1. 原样存入每日归档（永久完整保存）
        storage.append_daily_chat(user_msg, assistant_msg)

        # 2. 加入短期记忆
        new_block = f"---\n**User:** {user_msg}\n**Assistant:** {assistant_msg}"
        short_content = self.get_short_term_content() + new_block
        rounds = self._split_rounds(short_content)

        # 3. 超出轮数，旧的移入长期记忆
        while len(rounds) > self.short_term_max_round:
            old_round = rounds.pop(0)
            long_content = storage.read_md(storage.PATH_LONG_TERM)
            long_content += f"\n---\n{old_round}"
            storage.write_md(storage.PATH_LONG_TERM, long_content)

        new_short = "\n---\n".join(rounds)
        storage.write_md(storage.PATH_SHORT_TERM, new_short)

    # ---------------- 长期记忆分级压缩 ----------------
    def _get_compressed_long_term(self) -> str:
        long_content = storage.read_md(storage.PATH_LONG_TERM)
        rounds = self._split_rounds(long_content)
        if not rounds:
            return "无更早历史记忆"

        compressed = []
        total = len(rounds)
        for idx, item in enumerate(reversed(rounds)):
            progress = idx / max(total, 1)
            if progress < 0.3:
                ratio = 1.0
            elif progress < 0.6:
                ratio = 0.7
            elif progress < 0.85:
                ratio = 0.4
            else:
                ratio = 0.2

            keep_len = int(len(item) * ratio)
            cut_text = item[:keep_len] + ("..." if keep_len < len(item) else "")
            compressed.append(cut_text)

        return "\n\n---\n".join(reversed(compressed))

    # ---------------- 设置每日加载规则（关键新功能） ----------------
    def set_load_all_daily(self):
        """加载所有天数的每日记录"""
        self.load_all_daily = True
        self.load_specify_days = []

    def set_load_specify_days(self, date_list: list):
        """只加载指定某几天，例：["2026-05-01","2026-05-03"]"""
        self.load_all_daily = False
        self.load_specify_days = date_list

    def set_daily_compress_level(self, level: int):
        self.daily_compress_level = max(0, min(100, level))

    # ---------------- 读取每日记录 + 压缩 + 自动避开最近对话重叠 ----------------
    def _get_daily_history_content(self) -> str:
        # 拿到要加载的日期列表
        if self.load_all_daily:
            date_list = storage.get_all_daily_date_list()
        else:
            date_list = self.load_specify_days

        if not date_list:
            return ""

        all_daily_text = ""
        for date in date_list:
            path = storage.get_daily_md_path(date)
            if not os.path.exists(path):
                continue
            day_raw = storage.read_md(path)
            # 压缩当前天数内容
            day_compressed = sequential_sample_compress(day_raw, self.daily_compress_level)
            all_daily_text += f"\n## {date} 聊天记录\n{day_compressed}\n"

        return all_daily_text.strip()

    # ---------------- 组装最终上下文【固定顺序 + 无重叠】 ----------------
    def build_llm_context(self) -> str:
        # 1. 永久设定
        perm_text = self.get_permanent_content()

        # 2. 最近完整对话（独立块，不和每日重叠）
        short_text = self.get_short_term_content()

        # 3. 更早长期记忆
        long_text = self._get_compressed_long_term()

        # 4. 每日历史（可选全部天 / 指定某天，已自动隔离不重叠）
        daily_history = self._get_daily_history_content()

        # 固定顺序拼接
        context_parts = []
        context_parts.append("# 永久设定")
        context_parts.append(perm_text if perm_text else "无")

        context_parts.append("\n# 最近完整对话")
        context_parts.append(short_text if short_text else "暂无")

        context_parts.append("\n# 更早历史记忆（自动分级压缩）")
        context_parts.append(long_text)

        if daily_history:
            context_parts.append(f"\n# 每日历史聊天记录（压缩等级：{self.daily_compress_level}%）")
            context_parts.append(daily_history)

        return "\n".join(context_parts).strip()
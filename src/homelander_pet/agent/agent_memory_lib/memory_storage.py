import os
from datetime import datetime

DATA_ROOT = "agent_memory_data"
DAILY_DIR = os.path.join(DATA_ROOT, "daily")
PATH_PERMANENT = os.path.join(DATA_ROOT, "permanent.md")
PATH_SHORT_TERM = os.path.join(DATA_ROOT, "short_term.md")
PATH_LONG_TERM = os.path.join(DATA_ROOT, "long_term.md")


def set_data_root(data_root: str) -> None:
    global DATA_ROOT, DAILY_DIR, PATH_PERMANENT, PATH_SHORT_TERM, PATH_LONG_TERM
    DATA_ROOT = data_root
    DAILY_DIR = os.path.join(DATA_ROOT, "daily")
    PATH_PERMANENT = os.path.join(DATA_ROOT, "permanent.md")
    PATH_SHORT_TERM = os.path.join(DATA_ROOT, "short_term.md")
    PATH_LONG_TERM = os.path.join(DATA_ROOT, "long_term.md")

def init_storage():
    if not os.path.exists(DATA_ROOT):
        os.makedirs(DATA_ROOT)
    if not os.path.exists(DAILY_DIR):
        os.makedirs(DAILY_DIR)

PATH_PERMANENT = os.path.join(DATA_ROOT, "permanent.md")
PATH_SHORT_TERM = os.path.join(DATA_ROOT, "short_term.md")
PATH_LONG_TERM = os.path.join(DATA_ROOT, "long_term.md")

def read_md(path: str) -> str:
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def write_md(path: str, content: str):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def get_daily_md_path(date_str=None) -> str:
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(DAILY_DIR, f"{date_str}.md")

def append_daily_chat(user: str, assistant: str):
    init_storage()
    path = get_daily_md_path()
    now_time = datetime.now().strftime("%H:%M:%S")
    block = f"\n\n---\n### {now_time}\n**User:** {user}\n**Assistant:** {assistant}"
    with open(path, "a", encoding="utf-8") as f:
        f.write(block)

# 获取所有已存在的日期列表
def get_all_daily_date_list():
    if not os.path.exists(DAILY_DIR):
        return []
    files = os.listdir(DAILY_DIR)
    date_list = []
    for f in files:
        if f.endswith(".md"):
            date_list.append(f.replace(".md", ""))
    return sorted(date_list)
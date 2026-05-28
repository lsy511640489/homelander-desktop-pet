# Homelander Pet

本项目采用 GNU General Public License v3.0 only (GPL-3.0-only) 开源，衍生作品同样需要以 GPL-3.0-only 或兼容许可开源。

一个可扩展的自定义桌宠工程骨架，面向以下能力：

- 数字形象视频资产按动作名组织
- 动作表驱动桌面行为，例如点击、鼠标移动、拖拽、松开
- DeepSeek 大模型问答
- 股票行情跟踪，支持通过 `.env` 配置多支 A 股代码及持仓权重，例如 `股票代码:股数`，并按加权整体涨跌切换透明色
- 热点新闻整理，支持从 `.env` 配置的 RSS/Atom 源抓取当天新闻并按关键字提问，默认使用国内可访问的中文新闻源
- Skill / MCP 插件式扩展

## 推荐架构

```text
homelander/
  assets/
    videos/
      source/
      actions/
        idle/
        click/
        mouse_move/
        drag_start/
        drag_move/
        release/
        think/
        answer/
  config/
    action-table.example.json
    pet-profile.example.json
    plugins.example.json
  src/
    homelander_pet/
      adapters/
      agent/
      chat/
      core/
      models/
      main.py
  .env.example
  pyproject.toml
```

## 设计原则

1. 动作和媒体解耦，动作表只描述“做什么”和“用什么资源”。
2. 桌面操作和数字形象分层，视频资源可以单独替换。
3. DeepSeek、Skill、MCP 都放在 adapter 层，避免污染核心运行时。
4. 所有动作都从统一 registry 读取，便于热更新和扩展。
5. 对话代理单独放在 `src/homelander_pet/agent/`，聊天 UI 单独放在 `src/homelander_pet/chat/`。

## 目录用途

- `assets/videos/source/`：原始视频或原始导出资产。
- `assets/videos/actions/<action_name>/`：按动作名分组的视频资源，桌宠动作视频需要用户自行放入这里，推荐使用 `.mov` 格式。
- `config/action-table.example.json`：动作表示例。
- `config/pet-profile.example.json`：桌宠基础配置。
- `config/plugins.example.json`：Skill / MCP 插件配置示例。
- `src/homelander_pet/adapters/news_digest.py`：热点新闻抓取和日度整理。
- `src/homelander_pet/agent/`：DeepSeek 对话代理、技能调度和 MCP 调度。
- `src/homelander_pet/chat/`：独立聊天窗口。

## 下一步接入点

- 把真实视频文件放进 `assets/videos/actions/<action_name>/`。
- 把你自己的动作视频 `.mov` 放进 `assets/videos/actions/<action_name>/`，每个动作名对应一个或多个视频资源。
- 用 `config/action-table.example.json` 扩成正式动作表。
- 配置 `DEEPSEEK_API_KEY` 后，右键桌宠窗口或点“对话”按钮即可聊天。
- 在 `config/plugins.example.json` 里启用技能和 MCP 服务后，代理会自动把它们暴露给 DeepSeek。
- 如果想让 `daily_news` 自动读取热点新闻，可以在 `.env` 里配置 `HOMELANDER_PET_NEWS_FEEDS`；不配也会使用内置的国内默认 RSS 源。

## MCP 示例

仓库里已经放了一个最小可运行的 MCP server 示例，路径是 [mcp_server/mcp_echo_server.py](mcp_server/mcp_echo_server.py)。它提供四个工具：`echo`、`server_time`、`current_pnl` 和 `daily_news`。

`current_pnl` 会直接读取 `.env` 里的 `HOMELANDER_PET_STOCK_CODES`，按持仓数量和实时行情计算当日整体盈亏，并以人民币汇总输出，不再返回单股明细。

`daily_news` 会直接读取 `.env` 里的 `HOMELANDER_PET_NEWS_FEEDS`，自动整理当天热点新闻；你也可以传 `query` 只看某个主题，例如 AI、芯片、宏观。

默认插件配置现在不再自动启动这个示例 server，避免打包后依赖仓库里的相对路径脚本。要启用它，可以复制 [config/plugins.example.json](config/plugins.example.json) 并把自己的 MCP 服务配置进去。

### 当前 MCP 清单

当前 [config/plugins.example.json](config/plugins.example.json) 里已经接入的 MCP 服务如下：

- `demo-echo`
  - `echo`
  - `server_time`
  - `current_pnl`
  - `daily_news`

## Skill 使用说明

Skill 是这个工程里给大模型提供的“可调用能力”。它和 MCP 一样都由代理层统一接入，但更适合封装一类完整任务，比如选股、固定流程问答、领域助手。

### 1. 在配置里启用 Skill

在 [config/plugins.example.json](config/plugins.example.json) 的 `skills` 段里启用对应 skill，并确保 `entry` 指向实际目录。例如：

- `skills/a-share-xgboost-screen`：A 股 XGBoost / LightGBM 选股 skill
- `skills/skill-echo-test`：最小测试 skill，用于验证 skill 链路

### 2. Skill 的文件结构

每个 skill 目录里至少要有一个 [SKILL.md](skills/a-share-xgboost-screen/SKILL.md) 文件，用来描述这个 skill 的目标、输入、输出和执行方式。代理会读取这份说明，并把它传给大模型。

### 3. Skill 在代理里如何暴露

启用后，代理会把 skill 暴露成工具调用，工具名会变成 `skill__<normalized_name>`。例如：

- `a-share-xgboost-screen` -> `skill__a_share_xgboost_screen`
- `skill-echo-test` -> `skill__skill_echo_test`

模型在对话时可以直接调用这些工具，调用结果会出现在聊天记录里，也会被记入本地记忆系统。

### 4. 如何在对话里使用 Skill

你可以直接告诉桌宠要做什么，模型会根据 skill 描述自动选择工具。比如：

- “用选股 skill 帮我筛 5 只 A 股”
- “调用 `skill-echo-test` 测试一下 skill 链路”
- “按 `a-share-xgboost-screen` 的规则给我一个 brief 选股结果”

如果 skill 配置和目录都正确，代理会优先调用 skill，而不是自己编造结果。

### 当前 Skill 清单

当前 [config/plugins.example.json](config/plugins.example.json) 里已经接入的 skill 如下：

- `a-share-xgboost-screen`
  - 用途：A 股 XGBoost / LightGBM 选股
- `advogado-criminal`
  - 用途：法律顾问
- `skill-echo-test`
  - 用途：最小测试 skill，用于验证 skill 链路

## 运行方式

1. 直接启动桌宠窗口：`uv run python -m homelander_pet.main`
2. 如果你只想先看配置能否正常读取：`$env:HOMELANDER_PET_HEADLESS=1; uv run python -m homelander_pet.main`
3. 要启用对话，把 `DEEPSEEK_API_KEY` 写到环境变量里，再从桌宠窗口打开聊天窗。
4. 后续接入真实视频时，需要你自己把 `.mov` 动作视频放进 `assets/videos/actions/<action_name>/`，再把占位资源替换成实际素材。
5. 如果想让桌宠根据股票整体涨跌变色，可以在 `.env` 里配置 `HOMELANDER_PET_STOCK_CODES=513010:100,518600:200`。冒号后面代表持仓数量，程序会按加权整体涨跌判断颜色，整体上涨时切成红色、整体下跌时切成绿色。
6. 如果想让 `current_pnl` 自动读环境变量，请再加一条 `HOMELANDER_PET_STOCK_HOLDINGS=513010:5800:5.00,518600:500:1.00`，格式是 `代码:持仓数:买入均价`。
7. 如果想让 `daily_news` 自动抓取当天热点新闻，请配置 `HOMELANDER_PET_NEWS_FEEDS`；也可以直接在对话里问它某个主题，传 `query` 就行。


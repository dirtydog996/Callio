# Callio - 你的语音优先超级智能伙伴

🌐 语言： [English](README.md) | **简体中文**

![Callio Logo](app/shared/callio-logo.svg)

> “和你的代码说话，和你的想法说话，和未来说话。”

Callio 是一个基于大语言模型构建的语音优先超级智能个人助手，目标是彻底改变人和 AI 协作的方式。它不是一个只会接收命令并返回答案的普通语音助手，而是你心智的延伸，是你随时可以呼叫的“第二大脑”。

无论你在开车、做饭、散步，还是躺在沙发上闭目思考，只要拿起手机呼叫 Callio，你就可以和一个顶级智能伙伴进行深入讨论。Callio 不仅理解你的表达，还会在后台静默执行工作：拉取代码仓库、分析架构、读取数据、运行测试、生成文档，并在恰当时机给出恰当反馈。

Callio 不是被动的问答工具，而是主动协作者。对话过程中，它会持续理解上下文、预判你的需求，并主动提出建议。讨论结束后，它可以自动整理 TODO 清单，在你确认后直接执行任务，并把结果反馈给你，让对话不断流地持续下去。

我们的愿景是：让每个人都拥有一个始终在线、信息充分、主动协作的超级智能体。不是冷冰冰的聊天机器人，而是真正理解你、帮助你、与你共创的数字伙伴。Callio 完全开源并支持自托管，你的数据、代码和对话都由你掌控。

这不是 Siri。这不是 Alexa。这是 Callio。

## 为什么是 Callio

- 语音优先，支持基于 WebSocket 的全双工交互
- 会话级任务规划与异步执行
- Web、移动端、CLI 多端统一接入
- STT、TTS、LLM、Agent 后端可插拔
- 支持上下文延续与恢复，持续协作不断线

## 使用场景

### 1. 语音驱动的代码审查与性能优化

场景：你在下班路上，突然想到 `order-service` 的某个查询接口在大数据量下可能变慢。

你呼叫 Callio，让它检查该接口。Callio 自动拉取最新代码，分析 SQL 与索引命中情况，快速指出查询没有命中 `user_id` 与 `created_at` 的联合索引，导致了全表扫描，并主动询问是否要生成迁移脚本。

你确认后，回到家时 PR 已经准备好。

### 2. 架构方案讨论与功能迭代

场景：你在评估异步通知系统应该选 RabbitMQ 还是 Kafka。

Callio 会结合你当前架构和流量特征进行分析，解释为什么在现阶段 RabbitMQ 更合适，同时提示 Kubernetes 下的运维要点，并给出可执行落地方案。

讨论结束后，Callio 自动生成任务清单，在你确认后执行 Helm 清单、部署文档和 CI/CD 更新，并在 PR 就绪时通知你。

### 3. 线上故障定位与协作式调试

场景：生产环境出现内存持续增长，你需要尽快定位问题。

Callio 拉取监控与日志上下文，识别可疑组件，定位回归窗口，并给出回滚或代码修复建议。你可以继续通过语音追问，Callio 会实时验证假设并推进排查。

修复方案确认后，它还能自动跑测试并准备补丁供你评审。

### 4. 项目入职培训与知识传递

场景：团队有新成员加入，需要快速理解项目结构。

Callio 扫描代码仓库，梳理模块边界与数据流，生成结构化入门文档与简短讲解脚本。新成员可以先听后读，更快建立全局认知。

## 架构概览

核心模块：

- `callio/config`：运行时配置与环境变量
- `callio/core`：FastAPI 接口、SQLite 状态、内存中枢
- `callio/voice`：语音管线与音频后端集成
- `callio/worker`：任务分发、Agent 解析与执行沙箱脚手架
- `callio/meta`：发布与健康检查相关脚手架
- `app/web`、`app/mobile`、`app/cli`、`app/shared`：用户客户端

## 功能矩阵

- 语音优先交互，服务端统一编排 STT/TTS
- Web、移动端、CLI 共享前端资源
- 后台任务编排，支持进度追踪与日志记录
- 支持会话恢复，连续对话不中断
- 可插拔 STT 后端（`whisper`、`sensevoice`）
- 可插拔 TTS 后端（`chatt`、`say`、`edge`、`cosyvoice`、`fish`）
- 可插拔 Agent 后端（`hermes`、`openclaw`、`goose`、`aider`、`claude`）
- 可插拔 LLM 提供方（`ollama`、`openai`、`anthropic`、`gemini`、`openai_compatible`）

## 快速开始

```bash
python -m venv venv
./venv/bin/pip install -r requirements.txt

# 可选：国内网络建议使用 HuggingFace 镜像
export CALLIO_HF_ENDPOINT=https://hf-mirror.com

# 可选：检查 ChatTTS 依赖
./scripts/check-tts-deps.sh

# 启动服务
./venv/bin/python -m callio
```

建议使用 `venv` 中的 Python，避免系统环境或 conda 环境导致依赖解析不一致。

## 使用方式

### 启动服务

```bash
./venv/bin/python -m callio
```

### 设置向导

可通过交互式向导生成或更新 `.env`，一次性配置可运行所需的关键项
（LLM 提供方与模型、Ollama 地址与模型、STT/TTS 后端、服务端口、通知 webhook、Worker 运行参数等）。

```bash
./venv/bin/python -m callio setup
```

别名：

```bash
./venv/bin/python -m callio init
```

可选启动参数：

```bash
./venv/bin/python -m callio --no-qr
```

### ASGI 启动

```bash
./venv/bin/uvicorn callio.app:app --host 0.0.0.0 --port 8000
```

### CLI 示例

```bash
python app/cli/main.py health
python app/cli/main.py sessions
python app/cli/main.py dispatch --title "Plan tasks" --description "Break current work into background tasks"
```

### 客户端入口

- Web：`/app/web/index.html`
- Mobile：`/app/mobile/index.html`
- 兼容别名：`/static/index.html`

## 示例配置

可直接复制使用的配置示例位于 `/examples`：

- 本地 Ollama 快速配置：`examples/01-local-ollama`
- DeepSeek / Qwen / OpenAI 提供方配置：`examples/02-remote-llm-providers`
- 更高性能 ASR/TTS 配置：`examples/03-efficient-voice`

## 配置

### 关键环境变量

| 变量 | 默认值 | 说明 |
|----------|---------|-------------|
| `CALLIO_STT_BACKEND` | `whisper` | STT 后端（`whisper`、`sensevoice`） |
| `CALLIO_TTS_BACKEND` | `chatt` | TTS 后端（`chatt`、`say`、`edge`、`cosyvoice`、`fish`） |
| `CALLIO_AGENT_BACKEND` | _(empty)_ | 指定 Agent 后端（`hermes`、`openclaw`、`goose`、`aider`、`claude`） |
| `CALLIO_AGENT_COMMAND` | _(empty)_ | 自定义命令模板（包含 `{task}` 占位符） |
| `CALLIO_LLM_PROVIDER` | `ollama` | LLM 提供方（`ollama`、`openai`、`anthropic`、`gemini`、`openai_compatible`） |
| `CALLIO_LLM_MODEL` | `qwen2.5:7b` | 所选 LLM 提供方对应模型名 |
| `CALLIO_LLM_API_KEY` | _(empty)_ | 供应商 API Key（可回退到 `OPENAI_API_KEY`、`ANTHROPIC_API_KEY`、`GEMINI_API_KEY`） |
| `CALLIO_LLM_BASE_URL` | _(empty)_ | `openai_compatible` 或代理路由场景下的 Base URL 覆盖 |
| `CALLIO_OLLAMA_BASE_URL` | `http://localhost:11434/v1` | `CALLIO_LLM_PROVIDER=ollama` 时使用的 Ollama 地址 |
| `CALLIO_NOTIFY_WECHAT_WEBHOOK` | _(empty)_ | 会话结束摘要的企业微信 webhook |
| `CALLIO_NOTIFY_FEISHU_WEBHOOK` | _(empty)_ | 会话结束摘要的飞书 webhook |
| `CALLIO_NOTIFY_DISCORD_WEBHOOK` | _(empty)_ | 会话结束摘要的 Discord webhook |
| `CALLIO_NOTIFY_TELEGRAM_WEBHOOK` | _(empty)_ | 会话结束摘要的 Telegram webhook |
| `CALLIO_NOTIFY_TIMEOUT_SEC` | `8` | 通知请求超时时间（秒） |
| `CALLIO_PORT` | `8000` | 服务端口 |
| `CALLIO_HOST` | `0.0.0.0` | 服务监听地址 |
| `CALLIO_APP_DIR` | `./app` | 客户端工作区根目录 |

完整配置项见 `callio/config/settings.py`。

## API 与 WebSocket 端点

主要端点：

- `GET /api/v1/health`
- `GET /api/v1/tasks`
- `POST /api/v1/tasks/dispatch`
- `GET /api/v1/sessions`
- `POST /api/v1/sessions`
- `GET /api/v1/sessions/{session_id}/tasks`
- `POST /api/v1/sessions/{session_id}/tasks/confirm`
- `POST /api/v1/sessions/{session_id}/tasks/cancel`
- `POST /api/v1/tasks/{node_id}/cancel`
- `GET /api/v1/tasks/{node_id}/runs`
- `WS /ws/status`
- `WS /ws`

## 验证

```bash
./venv/bin/python -m compileall callio
python -m unittest discover tests
```

可选语音 E2E 冒烟测试：

```bash
./venv/bin/python scripts/e2e-voice-test.py
./venv/bin/python scripts/e2e-voice-test.py --two-round-resume
```

## 一起踏上这段旅程

Callio 正在快速迭代。我们相信语音是人与机器最自然的交互方式，而大语言模型让真正智能的对话成为现实。

欢迎 Star、Fork、提交 PR，一起打造每个人都值得拥有的个人 AI 伙伴。

仓库地址：https://github.com/dirtydog996/Callio

## 招募共建者

我们正在寻找愿意长期共建 Callio 的开源伙伴。

- 对语音优先 AI 产品有热情的产品思考者
- Python 与后端工程师（FastAPI、异步任务系统、编排）
- 语音工程师（STT/TTS 管线优化）
- 前端工程师（Web 与移动端语音交互体验）
- DevOps 与基础设施贡献者（自托管、部署、可观测性）
- 技术文档与社区维护者

如果你想一起把真正主动协作的 AI 伙伴做成开源标杆，欢迎提 Issue 介绍你的背景与想法，或直接发起 PR。

## License

本项目采用 MIT License 开源，详见 [LICENSE](LICENSE)。

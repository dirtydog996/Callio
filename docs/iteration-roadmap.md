# Callio 迭代优化路线图

本文档基于当前代码库与 `design.md` V1/V2 规约，梳理**已完成**、**待优化**与**分阶段迭代计划**。按「用户可感知价值 → 技术债 → 远期架构」排序。

---

## 一、当前基线（2026-06）

### 已交付

| 能力 | 状态 |
|------|------|
| 全双工语音（Whisper + Ollama + ChatTTS/say） | ✅ |
| 手机 HTTPS 测试（mkcert 脚本） | ✅ |
| V2 编排层 `orchestrator/` | ✅ |
| 通话中提议 / 确认 / 并行派发任务 | ✅ |
| 三类任务 SUMMARIZE / ANALYZE / EXECUTE | ✅ |
| 转写缓冲 + 挂断摘要 + `session_events` / `task_runs` | ✅ |
| `app/` 多端交互目录（web / mobile / cli） | ✅ |
| `/ws/status` + Copilot 风格任务面板 | ✅ |
| `GET /api/v1/sessions/{id}/tasks` | ✅ |
| `tests/` 单元测试基线 | ✅ |

### 主要缺口

| 缺口 | 影响 |
|------|------|
| Agent 仅自动识别 Hermes/Claude，OpenClaw 未接入 | 无法用你的主力 coding agent |
| `CALLIO_AGENT_COMMAND` 不传任务描述 | 自定义 agent 不可用 |
| `on_user_speech_start` 未挂到 transport | 打断体验不完整 |
| LLM 进度上下文仅连接时注入一次 | 通话中进度回灌不稳定 |
| ANALYZE 走 Ollama 而非仓库内只读工具 | 分析质量有限 |
| Docker 沙箱未实装 | 编码任务直接在宿主机跑 |
| TaskIQ/Redis 未接入 | 进程重启任务丢失 |
| meta/ 自进化未接入运行时 | 设计规约未落地 |

---

## 二、迭代总览

```
Phase 1  编码 Agent 打通          ← 1～2 天，立竿见影
Phase 2  通话体验打磨              ← 2～3 天
Phase 3  任务可靠性 & 可观测性     ← 3～5 天
Phase 4  记忆 & 上下文智能         ← 1 周
Phase 5  安全沙箱 & 生产化         ← 1～2 周
Phase 6  自进化 & 高可用（远期）   ← 按需
```

---

## 三、Phase 1 — 编码 Agent 打通（P0）

**目标：** 对话中说「写代码」→ 确认后**可靠**调用 Hermes / OpenClaw / 自定义 CLI。

### 1.1 Agent 解析器（`worker/agent_resolver.py`）✅

- `CALLIO_AGENT_BACKEND`：`hermes` / `openclaw` / `claude`
- `CALLIO_AGENT_COMMAND` 支持 `{task}` 占位符
- 自动检测顺序：hermes → openclaw → claude
- 无 agent 时明确 FAILED（不再模拟成功）

### 1.2 结构化编码 Prompt（`worker/prompt_builder.py`）✅

- `propose_tasks` 支持 `actions[]`，写入 `session_events`
- `EXECUTE` 派发前组装摘要 + 行动清单

### 2.1 动态进度回灌 ✅

- `voice/context_updater.py` + `SessionHook` 每轮用户转写后刷新 system prompt

### 2.3 确认交互增强 ✅（部分）

- `confirm_all` 工具参数
- `POST .../tasks/confirm` / `cancel` API
- 手机端待确认任务「确认/取消」按钮

### 2.4 TTS 延迟优化

| 项 | 做法 |
|----|------|
| 流式 TTS | 评估 Piper / CosyVoice streaming chunk |
| 下行采样率 | `CALLIO_AUDIO_OUT_SAMPLE_RATE=24000` 提升音质 |
| 首包 | LLM streaming token → 按句切 TTS（Pipecat 已有能力可接） |

### 验收标准

- [ ] 助手说话时用户插话，TTS 立即停止
- [ ] 用户问「进展如何」无需重复描述即可得到最新状态
- [ ] 手机可点按钮确认任务

---

## 五、Phase 3 — 任务可靠性 & 可观测性（P1）

**目标：** 后台任务可恢复、可追踪、可限流。

### 3.1 任务队列升级

```
当前：asyncio.create_task（进程内）
目标：TaskIQ + Redis（或先用 SQLite 队列作轻量替代）
```

模块：`worker/queue.py`

- 派发写入 `task_queue` 表
- 独立 worker 进程 `python -m callio.worker` 消费
- 支持重启后续跑

### 3.2 任务生命周期完善

| 能力 | 实现 |
|------|------|
| 取消 RUNNING | `POST /api/v1/tasks/{id}/cancel` + `cancel_proposal` 扩展 |
| 超时 | `CALLIO_TASK_TIMEOUT_SEC`，超时置 FAILED |
| 重试策略 | 按 `kind` 区分：EXECUTE 3 次，ANALYZE 1 次 |
| 并发全局上限 | `CALLIO_GLOBAL_MAX_PARALLEL` |

### 3.3 可观测性

- 结构化日志：`task_id`, `session_id`, `kind`, `duration_ms`
- `GET /api/v1/tasks/{node_id}/runs` — 返回 `task_runs` 详情
- 健康检查扩展：`active_tasks`, `queue_depth`

### 3.4 ANALYZE 增强

从「纯 Ollama 问答」升级为「仓库感知」：

```
analyze_runner:
  1. ripgrep / 读关键文件（限定 CALLIO_SANDBOX_ROOT）
  2. 将片段 + 问题送 Ollama
  3. 输出 Markdown 报告入 task_runs
```

### 验收标准

- [ ] 重启 Callio 后 PENDING 任务可继续
- [ ] 可取消长时间运行的 Hermes 任务
- [ ] API 可查询任意任务完整日志

---

## 六、Phase 4 — 记忆 & 上下文智能（P1）

**目标：** 跨通话记住用户项目与决策。

### 4.1 工作记忆外置

- Redis（或 SQLite KV）存最近 N 轮 token
- 语音连接时加载同 `session_id` 历史（支持「继续上次通话」）

### 4.2 语义记忆接入语音

- 通话前 `MemoryHub.search_semantic_memory(user_query)` 注入 system prompt
- 每次 `SUMMARIZE` 完成自动 `add_semantic_memory`

### 4.3 行动计划驱动提议

- `sessions.action_plan` 解析为结构化 JSON
- 新通话开始时 LLM 可见上次未完成项，主动提议 `propose_tasks`

### 4.4 多项目 / 工作区

- `CALLIO_SANDBOX_ROOT` 按 session 或用户选择切换
- `propose_tasks` 增加 `workspace` 字段

---

## 七、Phase 5 — 安全沙箱 & 生产化（P2）

### 5.1 Docker 沙箱实装（`worker/sandbox.py`）

- `CALLIO_USE_DOCKER=1` 时真正 `docker run` 隔离
- 只挂载 `sandbox_root:/workspace:rw`
- 网络 `none` 或 allowlist

### 5.2 Git 断点增强

- checkpoint 按 `node_id` 存 tag
- FAILED 后可选保留 diff 供用户 review

### 5.3 进程守护

- `scripts/run-with-watchdog.sh` 调用 `meta/sanity_checker`
- 健康检查失败 → 回滚 + 通知（design.md Watchdog 规约）

### 5.4 配置与部署

- `.env.example` 全量配置模板
- `docker-compose.yml`：Callio + Ollama + Redis

---

## 八、Phase 6 — 远期架构（P3）

| 项 | 说明 |
|----|------|
| LiveKit / WebRTC | 替代 WebSocket PCM，降低延迟与弱网问题 |
| 弱网重连 | 指数退避 + 15s 音频保持窗口 |
| meta/shadow_mgr | 蓝绿自升级流水线 |
| Flutter 原生客户端 | 替代 H5，更好 VoIP 后台 |
| 多用户 / 鉴权 | API token + session 隔离 |

---

## 九、推荐执行顺序（接下来 2 周）

| 周 | 交付 |
|----|------|
| **W1** | Phase 1 全部 + Phase 2.1 打断 + Phase 2.2 动态进度 |
| **W2** | Phase 2.3 UI 确认 + Phase 3.1 轻量队列 + Phase 3.4 ANALYZE 增强 |

### 本周可立即开工的三项（最小 diff、最大收益）

1. **`agent_resolver.py`** — OpenClaw + `{task}` 修复（你已有 openclaw）
2. **注册 barge-in** — `pipeline.py` 约 10 行
3. **动态 progress 注入** — 每轮转写后更新 system message

---

## 十、模块演进对照

```
当前                          Phase 1-2 后                    Phase 3-5 后
─────                         ───────────                     ───────────
worker/runner.py              worker/agent_resolver.py        worker/queue.py
  └ _resolve_command (脆)       └ 多 agent 统一                 └ TaskIQ/Redis
orchestrator/ (已有)          + context_refresh               + workspace_router
voice/pipeline.py             + barge-in + dynamic ctx        + streaming TTS
app/web + app/mobile         + 确认按钮 + 会话历史             + 多端统一交互
meta/ (闲置)                  —                               + watchdog 接入
```

---

## 十一、成功指标（每 Phase 可量化）

| 指标 | 当前 | Phase 2 目标 | Phase 5 目标 |
|------|------|--------------|--------------|
| 语音端到端首响 | ~2-5s（按句 TTS） | <1.5s（流式） | <800ms |
| EXECUTE 任务真实执行率 | 依赖 Hermes PATH | 100%（含 OpenClaw） | 100%（沙箱内） |
| 通话中进度问答准确 | 不稳定 | >90% | >95% |
| 任务重启丢失率 | 100% | <20%（SQLite 队列） | 0%（Redis） |
| 手机任务确认方式 | 仅语音 | 语音 + 按钮 | 语音 + 按钮 + 推送 |

---

## 相关文档

- [design.md](../design.md) — V1 规约 + V2 编排架构
- [voice-full-duplex.md](voice-full-duplex.md) — 语音架构
- [mobile-testing.md](mobile-testing.md) — 手机测试
- [README.md](../README.md) — 配置与启动

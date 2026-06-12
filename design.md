Callio (Call I/O) 工业级详细设计与系统实现规范 (LLM-Ready V1.0)

本规范为 Callio (通用自主声控 Agent 与自进化平台) 的工程级实现白皮书。旨在作为高阶代码生成 LLM（如 Claude Code, Cursor）的输入 Spec，以高解耦、高可用、极速响应、安全性为核心。

一、 系统总体架构设计 (System Architecture)

Callio 采用三层解耦架构：接入流控层 (Real-time Stream Engine)、业务逻辑与记忆中转层 (Core & Memory Hub) 以及 安全隔离异步执行层 (Sandboxed Worker)。

                    +---------------------------------------+
                    |           Client (多端接入)           |
                    |    (Flutter / H5 / WebRTC / Web)      |
                    +-------------------+-------------------+
                                        |
                 Audio (WebRTC)         |  State / Control (WebSocket / HTTP)
                                        v
+---------------------------------------+---------------------------------------+
| 1. 接入流控层 (Real-time Stream Engine)                                         |
|    - LiveKit Server (SFU)                                                     |
|    - Pipecat Gateway (STT/VAD -> Dialog LLM -> TTS)                           |
+---------------------------------------+---------------------------------------+
                                        | 异步派发 / Event Hub
                                        v
+---------------------------------------+---------------------------------------+
| 2. 核心与记忆层 (Core & Memory Hub)                                           |
|    - FastAPI HTTP / WebSocket Server (状态同步)                                |
|    - SQLite (工作/情景记忆) & ChromaDB (长期语义向量)                            |
|    - TaskIQ / Redis (任务分发队列)                                             |
+---------------------------------------+---------------------------------------+
                                        | 任务认领
                                        v
+---------------------------------------+---------------------------------------+
| 3. 安全执行层 (Sandboxed Worker)                                               |
|    - Docker Dev Sandboxes (项目开发沙箱)                                        |
|    - Claude Code / Hermes CLI Wrapper                                         |
|    - Shadow Build & Hot Swap Manager (自进化安全验证模块)                       |
+---------------------------------------+---------------------------------------+


核心解耦设计原则 (Decoupling Principles)：

语音与执行分离： 语音机器人（Pipecat）仅负责“听取脑暴、理清思路、标记要点”。一旦触发耗时的编码或测试任务，必须通过 TaskIQ 发送至 Redis 队列，严禁在语音 Session 线程中进行任何阻塞性操作（如编译、运行测试）。

状态共享源（Single Source of Truth）： 手机端看板、电脑端 API、以及 Pipecat 大脑看到的任务看板（Todo Table），均由本地 SQLite 数据库统一驱动，通过 SQLite Trigger 或 FastAPI Event Broker 实现毫秒级广播同步。

二、 架构规约与约束规范 (Architectural Constraints)

1. 通信规约

WebRTC 音频传输： 采用 LiveKit 协议。默认音频采样率 $16\text{ kHz}$，单声道，Opus 编码。

网络时延控制：

本地/局域网下，音频单向传输时延 $T_{\text{audio}} \le 150\text{ ms}$。

从用户说话结束（VAD 判定）到大语言模型开始输出语音，端到端延迟（STT + LLM First Token + TTS First Chunk） $T_{\text{response}} \le 800\text{ ms}$。

WebSocket 状态通道： 所有状态报文使用 JSON 格式。心跳间隔 $5\text{ s}$，重连最大尝试间隔 $10\text{ s}$。

2. 沙箱隔离规约

执行沙箱限制： 后端 Agent 执行代码编写和系统命令时，必须限制在专用的 Docker 容器中。

只读宿主： 宿主机代码项目目录以 -v /host/path/to/project:/workspace:rw 挂载。沙箱只能访问 /workspace，不允许拥有宿主机 / 根目录的写权限。

网络限制： 容器默认只允许访问受信任的 API 服务端口，防止其发起恶意 DDOS 攻击或外泄敏感凭证。

三、 模块详细设计与解耦 (Module Decoupling)

整个工程目录结构与模块解耦严格按照以下拓扑设计：

1. 项目目录树规约

callio/
├── config/                 # 全局配置模块
│   └── settings.py
├── core/                   # 核心与记忆中转服务
│   ├── database.py         # SQLite & Vector 数据库连接与初始化
│   ├── server.py           # FastAPI WebServer & WebSocket
│   └── memory.py           # 三层记忆机制（情景、工作、长期向量）
├── voice/                  # 接入流控层 (Pipecat)
│   ├── pipeline.py         # Pipecat 核心语音流动管理
│   ├── prompt.py           # 系统级双向对齐/脑暴 Prompt 模板
│   └── actions.py          # LLM 触发的 Function Calling 列表
├── worker/                 # 安全隔离异步执行层
│   ├── tasks.py            # TaskIQ/Celery 异步任务定义
│   ├── runner.py           # Claude Code/Hermes 调用包装器
│   └── sandbox.py          # Docker/E2B 容器管理
└── meta/                   # 自进化引擎
    ├── shadow_mgr.py       # 影子目录管理与蓝绿切换
    └── sanity_checker.py   # 自生自检、E2E连接验证


2. 模块 A：全双工语音管线 (voice/pipeline.py)

功能： 极低时延全双工语音桥接。

实现逻辑：

通过 livekit_client 接入 Room，初始化 Pipeline。

设置 SileroVAD：阈值设定为 $P_{\text{speech}} > 0.6$，静音判定时长 $500\text{ ms}$。

打断（Barge-In）中断控制流：

async def on_user_speech_start(transport, pipeline):
    # 1. 立即给 LiveKit 播发静音信令
    await transport.send_control_message({"action": "mute_tts"})
    # 2. 强行截断 TTS 缓冲队列
    pipeline.clear_buffers()
    # 3. 释放 LLM 的当前响应任务
    pipeline.cancel_current_task()


3. 模块 B：状态中心与多级记忆 (core/memory.py)

工作记忆 (Session)： 缓存在 Redis 中，记录最近 $10$ 次的未转录 Token。

情景记忆 (Episodic)： 挂断电话后触发，使用 SQLite 保存本次通话的 Markdown 结构化摘要及脑暴意图。

语义记忆 (Semantic)： 异步跑批，使用 ChromaDB 将历史待办及代码架构 AST 向量化：

$$\vec{V}_{\text{doc}} = \text{Embedding}(\text{AST\_Node\_Description})$$

SQLite 初始化 DDL 规约：

-- 会话表
CREATE TABLE IF NOT EXISTS sessions (
    session_id VARCHAR(36) PRIMARY KEY,
    title TEXT NOT NULL,
    transcript TEXT,
    summary TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 任务看板表
CREATE TABLE IF NOT EXISTS spec_nodes (
    node_id VARCHAR(36) PRIMARY KEY,
    session_id VARCHAR(36) REFERENCES sessions(session_id),
    feature_name TEXT NOT NULL,
    description TEXT,
    difficulty_level INTEGER DEFAULT 1,
    status VARCHAR(20) DEFAULT 'DRAFT', -- DRAFT, PENDING, RUNNING, SUCCESS, FAILED, BLOCKED
    error_log TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


4. 模块 C：沙箱任务执行器 (worker/runner.py)

核心逻辑：

监听 TaskIQ 派发的 EXECUTE_TODO 任务。

创建/重置开发沙箱（Docker）。

利用 Subprocess 流式捕获 claude code 输出，使用正则表达式匹配进程标准输出（Stdout），以持续提取执行进度百分比：

$$\text{Progress}_{\text{percent}} = \frac{N_{\text{passed\_tests}}}{N_{\text{total\_tests}}} \times 100\%$$

断点机制： Agent 在执行每一步前，必须生成 git diff 暂存。若报错，自动执行 git reset --hard 并返回上一级断点，重试次数阈值设定为 $3$ 次。

5. 模块 D：自进化引擎 (meta/shadow_mgr.py)

核心逻辑：

克隆自身库路径到 /callio/shadow。

在 shadow 目录下执行升级任务（调用 sandbox 在 shadow 目录跑 Claude Code 修改自身逻辑）。

自检度量模型 (Sanity Check)：
运行自检套件，计算 $\text{Sanity\_Score}$。公式定义为：

$$\text{Sanity\_Score} = \alpha \cdot \text{Api\_Test} + \beta \cdot \text{VAD\_Init} + \gamma \cdot \text{Database\_Migrate}$$

$$\text{其中，} \alpha = 0.3, \, \beta = 0.4, \, \gamma = 0.3, \quad \text{且必须满足 } \text{Sanity\_Score} = 1.0$$

热重载与蓝绿切换：
自检评分必须为 $1.0$。然后执行原子级软连接切换，并发送重启指令：

# 切换当前运行软链接
ln -sfn /callio/shadow /callio/active
# 热重启守护服务而不中断当前 LiveKit 通话 socket (利用 gunicorn HUP 信号)
kill -HUP $(cat /var/run/callio_api.pid)


四、 稳定性和性能保障设计 (Stability & Performance)

1. 弱网高容错

WebRTC 重连退避： 在客户端（App/H5）引入指数退避重连算法：

$$T_{\text{retry}} = \min(2^n \cdot 100\text{ ms}, \, 5000\text{ ms})$$

音频通道保持： 手机端接听后，强制声明 VoIP 后台音频模式。当 WebSocket 信令发生短时闪断时，保持音频流通道连接，在 $15\text{ s}$ 恢复窗口期内继续通话，避免由于网络颠簸导致挂机重播。

2. 代码自进化崩溃预防 (Watchdog Pattern)

为了防止 Callio 把自己改崩溃、从而导致用户彻底“断联”，主系统进程必须运行于进程守护（Supervisor/Systemd）下。

配置一个独立的、不被自进化代码修改的 Watchdog 进程：

Watchdog 每 $10\text{ s}$ 向本地 HTTP 端点 /api/v1/health 发送心跳检测。

如果心跳中断超过 $30\text{ s}$，Watchdog 强行重置软链接 /callio/active -> /callio/stable_backup，并在 $5\text{ s}$ 内强制杀死所有崩溃进程并冷启动恢复。

回滚成功后，Watchdog 绕过自进化代码直接向 LiveKit 音频服务端下发呼叫指令，呼唤用户：“主人，刚刚我尝试修改自己的语音管道逻辑失败并发生了严重崩溃，我已经成功完成了安全自我回滚，请查看刚才的异常日志。”

五、 初始化样板代码 (Boilerplate Implementation)

这部分代码是本系统启动的黄金代码。你可以将此代码直接喂给其他 LLM，作为它快速跑通 FastAPI + LiveKit + SQLite 框架的基础底座。

import os
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
import sqlite3

app = FastAPI(title="Callio API Gateway", version="1.0")
DB_PATH = "callio_local.db"

# 初始化本地 SQLite 存储
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS spec_nodes (
        node_id TEXT PRIMARY KEY,
        feature_name TEXT NOT NULL,
        description TEXT,
        status TEXT DEFAULT 'PENDING'
    )""")
    conn.commit()
    conn.close()

init_db()

class TodoItem(BaseModel):
    node_id: str
    feature_name: str
    description: str

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast_status(self, message: dict):
        for connection in self.active_connections:
            await connection.send_json(message)

manager = ConnectionManager()

# WebSocket 毫秒级多端状态同步通道
@app.websocket("/ws/status")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # 持续监听客户端指令或维持心跳
            data = await websocket.receive_text()
            await websocket.send_json({"status": "heartbeat", "received": data})
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# 派发异步执行任务接口
@app.post("/api/v1/tasks/dispatch")
async def dispatch_task(todo: TodoItem):
    # 1. 写入本地 SQLite
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO spec_nodes (node_id, feature_name, description, status) VALUES (?, ?, ?, ?)",
        (todo.node_id, todo.feature_name, todo.description, 'PENDING')
    )
    conn.commit()
    conn.close()

    # 2. 毫秒级广播状态至手机端 APP 看板
    await manager.broadcast_status({
        "event": "TASK_DISPATCHED",
        "node_id": todo.node_id,
        "feature_name": todo.feature_name,
        "status": "PENDING"
    })

    # 3. 异步唤醒 Sandbox Worker 运行 Claude Code (不阻塞当前 API 线程)
    asyncio.create_task(run_sandbox_worker(todo.node_id, todo.description))
    
    return {"status": "dispatched", "node_id": todo.node_id}

async def run_sandbox_worker(node_id: str, description: str):
    # 这里模拟沙箱后台多步骤执行
    await asyncio.sleep(5)  # 模拟慢长考
    # 更新 SQLite 为 RUNNING
    # 模拟执行成功，并通过 WebSocket 广播给多端
    await manager.broadcast_status({
        "event": "TASK_COMPLETED",
        "node_id": node_id,
        "status": "SUCCESS"
    })

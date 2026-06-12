# 全双工语音通信架构

## 目标

类似电话的语音对话体验：

- 用户持续说话，服务端实时检测、识别、回复
- 助手语音通过同一条 WebSocket **流式**回传到手机播放
- 用户可在助手说话时插话（Pipecat VAD + interruption 处理）

## 数据通道（单条 WebSocket `/ws`）

| 方向 | 格式 | 说明 |
|------|------|------|
| 手机 → Mac | 二进制 Int16 PCM @ 16kHz | 麦克风连续上行 |
| Mac → 手机 | 二进制 Int16 PCM @ 16kHz | TTS 分块下行 |
| 双向 | JSON 文本 | 转写、助手文字、`interrupt` 控制消息 |

这与「生成整段 WAV 再播放」不同：下行音频走 Pipecat `transport.output()` 的 **OutputAudioRawFrame** 流，与上行对称，符合全双工管道设计。

## 服务端管道

```
浏览器麦克风
  → transport.input() → VAD → Whisper STT
  → LLM (Ollama)
  → Mac TTS (ChatTTS 神经合成 → PCM 分块，失败时回退 say)
  → transport.output() → 浏览器扬声器
```

文本同时经 `WebSocketUIProcessor` 推到页面显示。

## 与纯本地方案的区别

| 模式 | 麦克风 | 听回复 |
|------|--------|--------|
| Mac 本机 `http://127.0.0.1` | 浏览器采集 | 浏览器播放下行 PCM |
| 手机 HTTPS | 浏览器采集 | 浏览器播放下行 PCM |
| 旧方案（已废弃） | 浏览器采集 | Mac 扬声器 / JSON+Audio 整段播放 |

## TTS 部署位置

**TTS 模型跑在 Mac 服务端**，手机只负责采集麦克风与播放下行 PCM，不在手机上跑模型。

| 后端 | 环境变量 | 说明 |
|------|----------|------|
| **ChatTTS**（默认） | `CALLIO_TTS_BACKEND=chatt` | 面向对话场景，中文自然度明显优于 `say` |
| macOS say（回退） | `CALLIO_TTS_BACKEND=say` | 无 PyTorch / ChatTTS 时，或加载失败时自动使用 |

### 模型来源与缓存

ChatTTS 权重从 **HuggingFace**（`2Noise/ChatTTS`）下载，不走 GitHub。缓存目录：

```
~/.cache/huggingface/hub/models--2Noise--ChatTTS/
```

国内建议设置镜像后再启动：

```bash
export CALLIO_HF_ENDPOINT=https://hf-mirror.com
./venv/bin/python -m callio
```

首次下载约 14 个文件，可能需要 10 分钟左右；之后启动直接从缓存加载。

可选：通过 `CALLIO_CHATTTS_HOME` 指定自定义 HuggingFace 缓存目录。

### 启动时预加载

与 Whisper 类似，默认在 FastAPI `startup` 时并行预加载：

| 变量 | 默认 | 说明 |
|------|------|------|
| `CALLIO_TTS_PRELOAD` | `1` | 启动时加载 ChatTTS |
| `CALLIO_WHISPER_PRELOAD` | `1` | 启动时加载 Whisper |

终端成功时会显示 `✅ ChatTTS 模型已就绪`。

### 后端选型说明

曾评估 CosyVoice / Fish Speech：

- **CosyVoice**：音质高，但需独立环境、模型较大，集成成本高
- **Fish Speech**：音质高，但 Mac MPS 推理极慢（数十秒/句），不适合实时通话
- **ChatTTS**：专为对话训练，安装简单，Mac 上可用于实时对话

## 依赖要求

ChatTTS 依赖 `transformers` 4.x 中的 `LlamaModel`，**不兼容 transformers 5.x**。

```bash
./scripts/check-tts-deps.sh          # 一键检查
./venv/bin/pip install 'transformers>=4.41,<5'  # 修复版本
```

必须用 venv 启动，避免 conda / 系统 Python 加载错误版本：

```bash
./venv/bin/python -m callio
```

## 限制与后续

- 当前按 **整句合成** 再切块发送，首包延迟高于 token 级流式 TTS
- 后续可接入流式 CosyVoice / Piper 进一步降低延迟
- 手机端必须使用 **HTTPS**（`./scripts/start-mobile-https.sh`）

## 相关文档

- [README 配置与故障排查](../README.md)
- [手机端 HTTPS 测试](mobile-testing.md)

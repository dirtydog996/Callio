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
| 双向 | JSON 文本 | 转写、助手文字、控制消息 |

这与「生成整段 WAV 再播放」不同：下行音频走 Pipecat `transport.output()` 的 **OutputAudioRawFrame** 流，与上行对称，符合全双工管道设计。

## 服务端管道

```
浏览器麦克风
  → transport.input() → VAD → Whisper STT
  → LLM (Ollama)
  → Mac TTS (say → PCM 分块)
  → transport.output() → 浏览器扬声器
```

文本同时经 `WebSocketUIProcessor` 推到页面显示。

## 与纯本地方案的区别

| 模式 | 麦克风 | 听回复 |
|------|--------|--------|
| Mac 本机 `http://127.0.0.1` | 浏览器采集 | 浏览器播放下行 PCM |
| 手机 HTTPS | 浏览器采集 | 浏览器播放下行 PCM |
| 旧方案（已废弃） | 浏览器采集 | Mac 扬声器 / JSON+Audio 整段播放 |

## 限制与后续

- 当前 TTS 使用 macOS `say` **按句合成** 再切块发送，首包延迟高于流式 TTS 模型
- 后续可替换为 Piper / 其他流式本地 TTS，进一步降低延迟
- 手机端必须使用 **HTTPS**（`./scripts/start-mobile-https.sh`）

# Callio iOS 客户端

Callio 的原生 iOS 客户端，使用 SwiftUI 构建，提供全双工语音交互体验。

## 功能特性

### 🎙️ 全双工语音对话
- 基于 WebSocket 的实时全双工语音通信
- 16kHz PCM 音频编解码，低延迟语音传输
- 支持打断（interruption）助手发言
- 流式文本转写与回复显示

### 💬 聊天界面
- 深色主题设计，与 Callio Web 端风格一致
- 实时消息流，支持流式显示
- 用户/助手消息气泡区分
- 语音录制状态指示与脉冲动画

### 📋 任务管理
- 后台任务实时同步
- 任务状态可视化（待确认/运行中/已完成/失败）
- 一键确认任务 / 批量确认
- 任务进度条与结果预览
- 手动派发任务

### 📚 会话历史
- 历史会话列表
- 会话详情与摘要
- 会话恢复（resume）支持
- 一键清除历史记录

### ⚙️ 设置中心
- 服务器地址与端口配置
- LLM 提供商选择（Ollama / DeepSeek / 通义千问 / Kimi / OpenAI 兼容）
- STT / TTS 后端配置
- 设置本地持久化与服务器同步

## 项目结构

```
app/ios/
├── Callio/                          # 主应用目录
│   ├── CallioApp.swift              # 应用入口 & 全局状态
│   ├── Info.plist                   # 应用配置
│   ├── Assets.xcassets/             # 资源文件
│   │   ├── AppIcon.appiconset/      # 应用图标
│   │   ├── AccentColor.colorset/    # 主题色
│   │   └── LaunchBackground.colorset/ # 启动页背景
│   ├── Models/                      # 数据模型
│   │   ├── ChatMessage.swift        # 聊天消息
│   │   ├── TaskItem.swift           # 任务项
│   │   ├── Session.swift            # 会话
│   │   └── AppSettings.swift        # 应用设置
│   ├── Services/                    # 服务层
│   │   ├── WebSocketService.swift   # WebSocket 通信
│   │   ├── AudioService.swift       # 音频录音与播放
│   │   └── APIService.swift         # REST API
│   └── Views/                       # 视图层
│       ├── RootView.swift           # 根视图 & 主题 & 组件
│       ├── ChatView.swift           # 聊天视图
│       ├── TaskListView.swift       # 任务列表
│       ├── SessionListView.swift    # 会话列表
│       └── SettingsView.swift       # 设置视图
└── README.md                        # 本文档
```

## 架构设计

### 整体架构
采用 MVVM 风格的单向数据流架构：

```
┌─────────────────────────────────────────────────┐
│                    Views                        │
│  (ChatView / TaskListView / SessionListView)    │
└───────────────────┬─────────────────────────────┘
                    │ @EnvironmentObject
                    ▼
┌─────────────────────────────────────────────────┐
│                  AppState                       │
│  (全局状态管理 + 业务逻辑调度)                  │
└─────────┬───────────────────┬───────────────────┘
          │                   │
          ▼                   ▼
┌─────────────────┐  ┌─────────────────┐
│  WebSocketService│  │   APIService    │
│  (语音实时通信)  │  │  (REST API 调用)│
└─────────────────┘  └─────────────────┘
          │
          ▼
┌─────────────────┐
│  AudioService   │
│ (录音 / 播放)   │
└─────────────────┘
```

### 通信协议
- **主 WebSocket** (`/ws`)：全双工语音通道
  - 上行：二进制 Int16 PCM @ 16kHz（麦克风音频）
  - 下行：二进制 Int16 PCM @ 16kHz（TTS 音频）
  - 双向：JSON 文本消息（会话/转写/助手文本/错误）

- **状态 WebSocket** (`/ws/status`)：任务状态实时推送

- **REST API** (`/api/v1/`)：会话管理、任务派发、设置同步

## 构建要求

- Xcode 15+
- iOS 17.0+
- Swift 5.9+
- 一个运行中的 Callio 服务端

## 快速开始

### 1. 创建 Xcode 项目

由于本仓库只包含 Swift 源代码，你需要在 Xcode 中创建项目并导入这些文件：

1. 打开 Xcode，选择 **File > New > Project**
2. 选择 **iOS > App**，点击 Next
3. 填写项目信息：
   - Product Name: `Callio`
   - Interface: `SwiftUI`
   - Language: `Swift`
   - 取消勾选 Core Data / Tests（可选）
4. 选择保存位置，创建项目

### 2. 导入源代码

将 `app/ios/Callio/` 目录下的所有文件（除 `Info.plist` 外）拖入 Xcode 项目：

- `CallioApp.swift` 替换原有的 `ContentView.swift` 和 App 入口文件
- `Models/`、`Services/`、`Views/` 文件夹整体拖入
- `Assets.xcassets/` 替换默认的 Assets
- 使用本目录下的 `Info.plist` 替换项目中的 Info.plist

### 3. 配置项目

1. 在 **Signing & Capabilities** 中配置你的开发者账号
2. 确保 Bundle Identifier 唯一
3. 确认 Deployment Target 为 iOS 17.0 或更高

### 4. 连接到 Callio 服务器

1. 确保你的 Callio 服务正在运行
2. 在 iOS 设备或模拟器上启动 App
3. 进入「设置」标签页
4. 填写服务器地址和端口（例如 `192.168.1.100` 和 `8000`）
5. 点击「保存设置」

> **注意**：如果使用真机测试，确保手机和服务器在同一局域网内，且服务器防火墙允许 8000 端口访问。

## 用户体验设计

### 语音交互流程
1. 用户打开 App，默认进入对话页面
2. 点击中央麦克风按钮开始语音会话
3. App 请求麦克风权限 → 连接 WebSocket → 开始录音
4. 用户说话，服务端实时转写并回复
5. 助手语音通过扬声器播放，文字同步显示
6. 用户可以随时打断助手发言
7. 再次点击按钮结束会话，显示会话总结

### 设计原则
- **深色主题**：保护用户夜间使用时的视力
- **脉冲动画**：录音状态有呼吸灯效果，直观反馈
- **极简操作**：核心操作只需一个按钮
- **实时反馈**：连接状态、消息流、任务进度实时更新
- **渐进式披露**：高级功能放在设置和二级页面

### 可访问性
- 支持动态字体大小
- 所有图标均有文本标签
- 高对比度配色方案
- VoiceOver 支持（SwiftUI 原生）

## 与其他客户端的对比

| 特性 | iOS 客户端 | Web 端 | Mobile Web | CLI |
|------|-----------|--------|------------|-----|
| 原生体验 | ✅ | ❌ | ❌ | ✅ |
| 推送通知 | 待实现 | ❌ | ❌ | ❌ |
| 后台音频 | ✅ | ❌ | ❌ | ❌ |
| 离线缓存 | 待实现 | ❌ | ❌ | ✅ |
| 跨平台 | ❌ | ✅ | ✅ | ✅ |
| 安装要求 | 需安装 | 浏览器 | 浏览器 | Python |

## 后续计划

- [ ] 锁屏界面控制（现在播放/暂停）
- [ ] 推送通知（任务完成提醒）
- [ ] 本地数据库持久化消息历史
- [ ]  Siri Shortcuts 集成
- [ ] Apple Watch 配套 App
- [ ]  Widget 支持
- [ ]  多语言支持（中/英）
- [ ]  语音指令快捷操作

## 常见问题

### Q: 为什么连接不上服务器？
A: 请检查：
1. 服务器地址和端口是否正确
2. 手机和服务器是否在同一网络
3. 服务器防火墙是否允许对应端口
4. 是否需要 HTTPS（在设置中开启）

### Q: 麦克风权限被拒绝了怎么办？
A: 进入 iOS 「设置 > 隐私与安全性 > 麦克风」，找到 Callio 并开启权限。

### Q: 语音有延迟怎么办？
A: 全双工语音对网络要求较高，建议：
1. 使用 5G WiFi 而非蜂窝网络
2. 确保服务器和客户端在同一局域网
3. 检查服务器 CPU 使用率（Whisper 和 TTS 均消耗算力）

### Q: 支持哪些 LLM 提供商？
A: 支持 Ollama（本地）、DeepSeek、通义千问、Kimi，以及任何 OpenAI 兼容的 API。

## 许可证

与 Callio 主项目保持一致。

# 用户交互端说明

Callio 现在将所有用户交互端统一收敛到顶层 `app/` 目录，便于按端维护体验、共享资源与扩展测试。

## 目录结构

```text
app/
├── cli/
│   └── main.py
├── mobile/
│   └── index.html
├── shared/
│   ├── client.css
│   └── client.js
└── web/
    └── index.html
```

## 各端职责

### Web 端

- 地址：`/app/web/index.html`
- 用途：桌面协作主界面
- 特点：
  - 类 GitHub Copilot App 的三栏布局
  - 左侧历史会话
  - 中间语音对话流与手动任务输入
  - 右侧后台任务状态与操作

### Mobile 端

- 地址：`/app/mobile/index.html`
- 用途：手机扫码进入后的语音协作页
- 特点：
  - 复用共享样式与逻辑
  - 针对窄屏布局优化
  - 保留任务确认、手动派发与语音会话入口

### CLI 端

- 入口：`python app/cli/main.py`
- 用途：在终端中操作会话与任务
- 当前支持：
  - `health`
  - `sessions`
  - `tasks [--session-id ...]`
  - `dispatch --title ... --description ...`
  - `confirm-all <session_id>`
  - `cancel-running <node_id>`

示例：

```bash
python app/cli/main.py health
python app/cli/main.py sessions
python app/cli/main.py tasks --session-id <session_id>
python app/cli/main.py dispatch --title "整理清单" --description "整理当前需求并拆成任务"
```

## 路由与兼容性

- 根路径 `/` 默认重定向到 `/app/web/index.html`
- `/static/index.html` 仍保留，兼容历史入口
- 终端二维码默认指向 `/app/mobile/index.html`

## 测试建议

- 单元测试：`python -m unittest discover tests`
- 桌面端：打开 `/app/web/index.html`
- 手机端：通过 `./scripts/start-mobile-https.sh` 打开 `/app/mobile/index.html`

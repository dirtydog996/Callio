# 手机端语音测试指南

Callio 的 Web 语音客户端通过浏览器采集麦克风，经 WebSocket 将 PCM 音频发送到 Mac 上的服务。Mac 本机测试通常可直接使用，手机端需要额外注意 **HTTPS** 与 **麦克风权限**。

## 为什么 Mac 可以、手机不行？

浏览器把页面是否「安全」作为能否调用麦克风的条件之一：

| 环境 | 典型地址 | 是否安全上下文 | 麦克风 |
|------|----------|----------------|--------|
| Mac 本机 | `http://127.0.0.1:8000` | 是 | 可用 |
| 手机局域网 HTTP | `http://192.168.x.x:8000` | 否 | **通常被拒绝** |
| 手机 HTTPS | `https://192.168.x.x:8000` | 是 | 可用 |
| 公网隧道 HTTPS | `https://xxxx.ngrok-free.app/...` | 是 | 可用 |

因此：

- Mac 浏览器打开 `http://127.0.0.1:8000` 可以正常录音。
- 手机扫描终端二维码（`http://局域网 IP`）时，Safari / Chrome 往往**不允许申请麦克风**，页面会卡在「请允许使用麦克风」或直接报错。

**手机测试必须使用 HTTPS。**

## 相关配置

| 变量 | 说明 |
|------|------|
| `CALLIO_SSL_CERT` | HTTPS 证书路径（手机测试必填） |
| `CALLIO_SSL_KEY` | HTTPS 私钥路径 |
| `CALLIO_PORT` | 服务端口，默认 `8000` |

启用 HTTPS 后，启动时终端二维码会自动使用 `https://` 链接。

证书文件建议放在项目 `certs/` 目录（已在 `.gitignore` 中忽略）。

---

## 方案一：mkcert + HTTPS（推荐）

同一 WiFi 下扫码访问，延迟低，适合日常开发。

### 一键启动（推荐）

```bash
./scripts/start-mobile-https.sh
```

脚本会自动：检查/安装 `mkcert`、生成本地 CA、按当前局域网 IP 生成或复用证书、以 HTTPS 启动 Callio 并打印二维码。

局域网 IP 变化时会自动重新生成证书。跳过二维码：`./scripts/start-mobile-https.sh --no-qr`

### 手动步骤（可选）

**1. 在 Mac 上生成证书**

```bash
brew install mkcert
mkcert -install

LAN_IP=$(ipconfig getifaddr en0)
mkdir -p certs
mkcert -cert-file certs/callio.pem -key-file certs/callio-key.pem "$LAN_IP" localhost 127.0.0.1
```

**2. 启动 HTTPS 服务**

```bash
export CALLIO_SSL_CERT=certs/callio.pem
export CALLIO_SSL_KEY=certs/callio-key.pem
python -m callio
```

终端应显示：

- 链接为 `https://192.168.x.x:8000/static/index.html`
- 提示「已启用 HTTPS，手机端可使用麦克风」

### 3. 手机操作

1. 手机与 Mac 连接**同一 WiFi**
2. 扫描终端中的小二维码，或手动输入 HTTPS 地址
3. 处理证书信任（首次访问）：
   - **iPhone**
     1. 在 Mac 执行 `mkcert -CAROOT`，找到根证书目录
     2. 将 `rootCA.pem` AirDrop 到 iPhone 并安装描述文件
     3. 打开 **设置 → 通用 → 关于本机 → 证书信任设置**，启用 mkcert 根证书
     4. 或在 Safari 中访问页面，按提示继续
   - **Android Chrome**：出现警告时选择继续访问即可
4. 点击「**开始对话**」
5. 在系统弹窗中选择「**允许**」麦克风
6. 状态变为「**正在录音，请说话...**」后即可测试

---

## 方案二：ngrok 隧道（快速验证）

无需自签证书，适合临时演示或外网访问。注意流量经 ngrok 中转，延迟略高于局域网。

### 1. 启动 Callio（可不显示二维码）

```bash
python -m callio --no-qr
```

### 2. 启动 ngrok

另开一个终端：

```bash
ngrok http 8000
```

### 3. 手机访问

用手机浏览器打开 ngrok 提供的 HTTPS 地址，例如：

```text
https://xxxx.ngrok-free.app/static/index.html
```

按页面提示允许麦克风即可。

---

## 启动顺序说明（前端行为）

为避免 iOS 上用户点击手势失效，页面按以下顺序启动：

1. 用户点击「开始对话」
2. **立即**请求麦克风权限（显示「请允许使用麦克风...」）
3. 权限通过后连接 WebSocket（显示「正在连接服务...」）
4. 成功后显示「正在录音，请说话...」

若权限被拒绝或环境不安全，会弹出具体错误提示。

---

## 常见问题

### 页面一直停在「请允许使用麦克风...」

- 检查是否使用了 **HTTPS** 地址（不是 `http://192.168.x.x`）
- 查看是否弹出系统权限框，需点「允许」
- iPhone：到 **设置 → Safari → 麦克风**，确认未禁用
- 若之前点过「拒绝」，需在浏览器网站设置中重新授权

### 弹出「麦克风权限被拒绝」

在浏览器设置中找到该站点，将麦克风权限改为「允许」，刷新页面重试。

### 弹出「当前访问方式不支持麦克风」

说明页面不在安全上下文中。请改用本文的 **HTTPS 方案**，不要继续用 HTTP 局域网地址。

### Mac 正常、手机仍失败

1. 确认二维码链接以 `https://` 开头
2. 确认 iPhone 已信任 mkcert 根证书（方案一）
3. 确认手机与 Mac 在同一局域网（方案一）
4. 换 Chrome / Safari 再试，避免微信内置浏览器（权限策略更严）

### 服务无法 Ctrl+C 退出

已修复：Pipecat 不再拦截 SIGINT，按一次 Ctrl+C 应能正常退出。若仍有活跃语音连接，会先取消管道再关闭 uvicorn。

---

## 参考

- 项目 README：[配置项与本地启动](../README.md)
- mkcert 文档：<https://github.com/FiloSottile/mkcert>
- ngrok 文档：<https://ngrok.com/docs>

//
//  WebSocketService.swift
//  Callio
//
//  WebSocket 服务 - 全双工语音通信
//

import Foundation

/// WebSocket 服务
final class WebSocketService {
    // MARK: - 回调
    var onSessionConnected: ((_ sessionId: String, _ resumed: Bool) -> Void)?
    var onTranscription: ((_ text: String) -> Void)?
    var onAssistantText: ((_ text: String, _ isStreaming: Bool) -> Void)?
    var onError: ((_ title: String, _ message: String) -> Void)?
    var onDisconnect: (() -> Void)?
    var onAudioData: ((_ data: Data) -> Void)?
    var onTaskEvent: ((_ event: TaskEvent) -> Void)?
    
    // MARK: - 属性
    private var webSocket: URLSessionWebSocketTask?
    private var statusWebSocket: URLSessionWebSocketTask?
    private var urlSession: URLSession?
    private var isConnected = false
    private var isDisconnecting = false
    private var currentHost: String = ""
    private var currentPort: String = ""
    private var useHTTPS: Bool = false
    private var resumeSessionId: String? = nil

    // 重连参数
    private var shouldAutoReconnect = false
    private var reconnectAttempts = 0
    private let maxReconnectAttempts = 10
    private var reconnectTimer: DispatchSourceTimer?
    
    // 目标采样率（与服务端一致）
    static let targetSampleRate: Double = 16000
    
    init() {
        let config = URLSessionConfiguration.default
        self.urlSession = URLSession(configuration: config, delegate: nil, delegateQueue: nil)
    }
    
    // MARK: - 连接管理
    
    /// 连接到语音 WebSocket
    func connect(host: String, port: String, resumeSessionId: String? = nil, useHTTPS: Bool = false) {
        self.currentHost = host
        self.currentPort = port
        self.useHTTPS = useHTTPS
        self.resumeSessionId = resumeSessionId
        self.shouldAutoReconnect = true
        self.reconnectAttempts = 0
        self.isDisconnecting = false
        establishConnection()
    }

    private func establishConnection() {
        
        let scheme = useHTTPS ? "wss" : "ws"
        var urlString = "\(scheme)://\(host):\(port)/ws"
        
        if let resumeId = resumeSessionId,
           let encodedId = resumeId.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) {
            urlString += "?resume_session_id=\(encodedId)"
        }
        
        guard let url = URL(string: urlString) else {
            onError?("连接错误", "无效的服务器地址")
            return
        }
        
        guard let session = urlSession else { return }
        
        webSocket = session.webSocketTask(with: url)
        isConnected = true
        
        receiveMessage()
        webSocket?.resume()
        
        // 同时连接状态 WebSocket
        connectStatusSocket(host: host, port: port, useHTTPS: useHTTPS)
    }
    
    /// 断开连接
    func disconnect() {
        isDisconnecting = true
        shouldAutoReconnect = false
        cancelReconnectTimer()
        isConnected = false
        webSocket?.cancel(with: .normalClosure, reason: nil)
        webSocket = nil

        statusWebSocket?.cancel(with: .normalClosure, reason: nil)
        statusWebSocket = nil

        onDisconnect?()
    }

    // MARK: - 自动重连

    private func scheduleReconnect() {
        guard shouldAutoReconnect else { return }
        guard reconnectAttempts < maxReconnectAttempts else {
            onError?("连接超时", "已达到最大重连次数 (\(maxReconnectAttempts))，请检查服务器状态后重试。")
            shouldAutoReconnect = false
            return
        }

        reconnectAttempts += 1
        let delay = min(pow(2.0, Double(reconnectAttempts)) * 0.1, 5.0)

        cancelReconnectTimer()
        let timer = DispatchSource.makeTimerSource()
        timer.schedule(deadline: .now() + delay)
        timer.setEventHandler { [weak self] in
            guard let self = self, self.shouldAutoReconnect else { return }
            self.establishConnection()
        }
        timer.resume()
        reconnectTimer = timer
    }

    private func cancelReconnectTimer() {
        reconnectTimer?.cancel()
        reconnectTimer = nil
    }
    
    // MARK: - 状态 WebSocket
    
    private func connectStatusSocket(host: String, port: String, useHTTPS: Bool) {
        let scheme = useHTTPS ? "wss" : "ws"
        guard let url = URL(string: "\(scheme)://\(host):\(port)/ws/status") else { return }
        guard let session = urlSession else { return }
        
        statusWebSocket = session.webSocketTask(with: url)
        receiveStatusMessage()
        statusWebSocket?.resume()
    }
    
    private func receiveStatusMessage() {
        statusWebSocket?.receive { [weak self] result in
            guard let self = self, self.isConnected else { return }
            
            switch result {
            case .success(let message):
                switch message {
                case .string(let text):
                    self.handleStatusTextMessage(text)
                case .data:
                    break
                @unknown default:
                    break
                }
                self.receiveStatusMessage()
                
            case .failure:
                // 状态连接失败不影响主连接
                break
            }
        }
    }
    
    private func handleStatusTextMessage(_ text: String) {
        guard let data = text.data(using: .utf8),
              let event = try? JSONDecoder().decode(TaskEvent.self, from: data) else {
            return
        }
        onTaskEvent?(event)
    }
    
    // MARK: - 消息接收
    
    private func receiveMessage() {
        webSocket?.receive { [weak self] result in
            guard let self = self, self.isConnected else { return }
            
            switch result {
            case .success(let message):
                switch message {
                case .data(let data):
                    // 二进制数据 = PCM 音频
                    self.onAudioData?(data)
                    
                case .string(let text):
                    // 文本消息 = JSON 控制消息
                    self.handleTextMessage(text)
                    
                @unknown default:
                    break
                }
                
                // 继续接收下一条消息
                self.receiveMessage()
                
            case .failure(let error):
                if self.isConnected {
                    self.onError?("连接错误", error.localizedDescription)
                }
                self.isConnected = false
                if !self.isDisconnecting && self.shouldAutoReconnect {
                    self.scheduleReconnect()
                } else {
                    self.onDisconnect?()
                }
        }
    }
    
    private func handleTextMessage(_ text: String) {
        guard let data = text.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let type = json["type"] as? String else {
            return
        }
        
        switch type {
        case "session":
            let sessionId = json["session_id"] as? String ?? ""
            let resumed = json["resumed"] as? Bool ?? false
            onSessionConnected?(sessionId, resumed)
            
        case "transcription":
            let text = json["text"] as? String ?? ""
            onTranscription?(text)
            
        case "assistant":
            let text = json["text"] as? String ?? ""
            onAssistantText?(text, true)
            
        case "error":
            let title = json["title"] as? String ?? "语音错误"
            let message = json["text"] as? String ?? "发生未知错误"
            onError?(title, message)
            
        case "interrupt":
            // 中断消息 - 停止播放
            onAssistantText?("", true) // 触发重置
            
        default:
            break
        }
    }
    
    // MARK: - 发送音频数据
    
    /// 发送 PCM 音频数据
    func sendAudioData(_ data: Data) {
        guard isConnected else { return }
        
        webSocket?.send(.data(data)) { [weak self] error in
            if let error = error {
                print("发送音频数据失败: \(error.localizedDescription)")
                self?.onError?("发送失败", error.localizedDescription)
            }
        }
    }
    
    /// 发送文本消息
    func sendTextMessage(_ message: [String: Any]) {
        guard isConnected,
              let data = try? JSONSerialization.data(withJSONObject: message),
              let text = String(data: data, encoding: .utf8) else {
            return
        }
        
        webSocket?.send(.string(text)) { error in
            if let error = error {
                print("发送文本消息失败: \(error.localizedDescription)")
            }
        }
    }
}

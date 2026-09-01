//
//  CallioApp.swift
//  Callio
//
//  Callio iOS 客户端 - 全双工语音交互应用
//

import SwiftUI

@main
struct CallioApp: App {
    @StateObject private var appState = AppState()
    
    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(appState)
                .preferredColorScheme(.dark)
                .statusBar(hidden: false)
        }
    }
}

// MARK: - 全局应用状态

/// 全局应用状态，管理所有核心服务和数据
final class AppState: ObservableObject {
    // 服务
    let apiService = APIService()
    let webSocketService = WebSocketService()
    let audioService = AudioService()
    
    // 数据
    @Published var messages: [ChatMessage] = []
    @Published var tasks: [TaskItem] = []
    @Published var sessions: [Session] = []
    @Published var settings = AppSettings()
    
    // 连接状态
    @Published var isConnected = false
    @Published var isRecording = false
    @Published var connectionStatus: ConnectionStatus = .disconnected
    @Published var statusMessage = "未连接"
    
    // 当前会话
    @Published var currentSessionId: String?
    @Published var selectedSessionId: String?
    
    // 错误
    @Published var errorMessage: String?
    @Published var showError = false
    
    init() {
        setupBindings()
        loadSettings()
    }
    
    private func setupBindings() {
        webSocketService.onSessionConnected = { [weak self] sessionId, resumed in
            DispatchQueue.main.async {
                self?.currentSessionId = sessionId
                self?.isConnected = true
                self?.connectionStatus = .connected
                self?.statusMessage = resumed ? "会话已恢复" : "语音已连接，可以开始说话了"
            }
        }
        
        webSocketService.onTranscription = { [weak self] text in
            DispatchQueue.main.async {
                self?.addMessage(role: .user, text: text)
            }
        }
        
        webSocketService.onAssistantText = { [weak self] text, isStreaming in
            DispatchQueue.main.async {
                if isStreaming, let last = self?.messages.last, last.role == .assistant, last.isStreaming {
                    self?.messages[self!.messages.count - 1].text += text
                } else {
                    self?.addMessage(role: .assistant, text: text, isStreaming: isStreaming)
                }
            }
        }
        
        webSocketService.onError = { [weak self] title, message in
            DispatchQueue.main.async {
                self?.errorMessage = "\(title): \(message)"
                self?.showError = true
                self?.statusMessage = title
                self?.connectionStatus = .error
            }
        }
        
        webSocketService.onDisconnect = { [weak self] in
            DispatchQueue.main.async {
                self?.isConnected = false
                self?.isRecording = false
                self?.connectionStatus = .disconnected
                self?.statusMessage = "已断开连接"
            }
        }
        
        webSocketService.onAudioData = { [weak self] data in
            self?.audioService.playPCMData(data)
        }
        
        webSocketService.onTaskEvent = { [weak self] event in
            DispatchQueue.main.async {
                self?.handleTaskEvent(event)
            }
        }
    }
    
    private func loadSettings() {
        if let saved = AppSettings.load() {
            settings = saved
        }
    }
    
    func saveSettings() {
        settings.save()
    }
    
    // MARK: - 消息管理
    
    private func addMessage(role: ChatRole, text: String, isStreaming: Bool = false) {
        let message = ChatMessage(
            id: UUID(),
            role: role,
            text: text,
            timestamp: Date(),
            isStreaming: isStreaming
        )
        messages.append(message)
    }
    
    // MARK: - 语音会话控制
    
    func startVoiceSession() {
        guard !settings.serverHost.isEmpty else {
            errorMessage = "请先在设置中配置服务器地址"
            showError = true
            return
        }
        
        messages.removeAll()
        connectionStatus = .connecting
        statusMessage = "正在连接..."
        
        audioService.requestRecordingPermission { [weak self] granted in
            guard let self = self else { return }
            if granted {
                self.audioService.startRecording { [weak self] pcmData in
                    self?.webSocketService.sendAudioData(pcmData)
                }
                self.webSocketService.connect(
                    host: self.settings.serverHost,
                    port: self.settings.serverPort,
                    resumeSessionId: self.selectedSessionId
                )
                self.isRecording = true
            } else {
                DispatchQueue.main.async {
                    self.errorMessage = "需要麦克风权限才能进行语音对话"
                    self.showError = true
                    self.connectionStatus = .disconnected
                }
            }
        }
    }
    
    func stopVoiceSession() {
        webSocketService.disconnect()
        audioService.stopRecording()
        audioService.stopPlayback()
        isRecording = false
        isConnected = false
        connectionStatus = .disconnected
        statusMessage = "会话已结束"
        
        // 刷新会话列表
        Task {
            await loadSessions()
        }
    }
    
    // MARK: - 会话管理
    
    @MainActor
    func loadSessions() async {
        do {
            sessions = try await apiService.fetchSessions()
        } catch {
            errorMessage = "加载会话列表失败: \(error.localizedDescription)"
            showError = true
        }
    }
    
    @MainActor
    func loadSessionTasks(sessionId: String) async {
        do {
            tasks = try await apiService.fetchTasks(sessionId: sessionId)
        } catch {
            errorMessage = "加载任务列表失败: \(error.localizedDescription)"
            showError = true
        }
    }
    
    func selectSession(_ session: Session) {
        selectedSessionId = session.sessionId
    }
    
    // MARK: - 任务管理
    
    private func handleTaskEvent(_ event: TaskEvent) {
        // 根据事件类型更新任务列表
        let interestingEvents = [
            "TASK_PROPOSED", "TASK_CONFIRMED", "TASK_RUNNING",
            "TASK_PROGRESS", "TASK_COMPLETED", "SUMMARY_UPDATED"
        ]
        
        guard interestingEvents.contains(event.event) else { return }
        
        let nodeId = event.nodeId ?? "\(event.event)-\(Date().timeIntervalSince1970)"
        
        if let index = tasks.firstIndex(where: { $0.nodeId == nodeId }) {
            tasks[index].update(with: event)
        } else {
            let task = TaskItem(from: event)
            tasks.insert(task, at: 0)
        }
    }
    
    @MainActor
    func dispatchTask(title: String, description: String) async {
        let sessionId = currentSessionId ?? selectedSessionId
        do {
            let _ = try await apiService.dispatchTask(
                title: title,
                description: description,
                sessionId: sessionId
            )
            if let sid = sessionId {
                await loadSessionTasks(sessionId: sid)
            }
        } catch {
            errorMessage = "派发任务失败: \(error.localizedDescription)"
            showError = true
        }
    }
    
    @MainActor
    func confirmTask(nodeId: String) async {
        guard let sessionId = currentSessionId ?? selectedSessionId else { return }
        do {
            let _ = try await apiService.confirmTask(sessionId: sessionId, nodeIds: [nodeId])
            await loadSessionTasks(sessionId: sessionId)
        } catch {
            errorMessage = "确认任务失败: \(error.localizedDescription)"
            showError = true
        }
    }
    
    @MainActor
    func cancelTask(nodeId: String) async {
        guard let sessionId = currentSessionId ?? selectedSessionId else { return }
        do {
            let _ = try await apiService.cancelTask(sessionId: sessionId, nodeIds: [nodeId])
            await loadSessionTasks(sessionId: sessionId)
        } catch {
            errorMessage = "取消任务失败: \(error.localizedDescription)"
            showError = true
        }
    }
    
    @MainActor
    func confirmAllTasks() async {
        guard let sessionId = currentSessionId ?? selectedSessionId else { return }
        do {
            let _ = try await apiService.confirmTask(sessionId: sessionId, nodeIds: [], confirmAll: true)
            await loadSessionTasks(sessionId: sessionId)
        } catch {
            errorMessage = "批量确认失败: \(error.localizedDescription)"
            showError = true
        }
    }
}

// MARK: - 连接状态枚举

enum ConnectionStatus {
    case disconnected
    case connecting
    case connected
    case error
    
    var color: Color {
        switch self {
        case .disconnected: return .gray
        case .connecting: return .yellow
        case .connected: return .green
        case .error: return .red
        }
    }
    
    var icon: String {
        switch self {
        case .disconnected: return "wifi.slash"
        case .connecting: return "wifi"
        case .connected: return "wifi.circle.fill"
        case .error: return "exclamationmark.triangle.fill"
        }
    }
}

//
//  ChatView.swift
//  Callio
//
//  聊天视图 - 语音对话主界面
//

import SwiftUI

/// 聊天视图
struct ChatView: View {
    @EnvironmentObject var appState: AppState
    @State private var scrollProxy: ScrollViewProxy?
    @State private var showTaskComposer = false
    @State private var taskTitle = ""
    @State private var taskDescription = ""
    @State private var isDispatching = false
    @State private var audioLevel: CGFloat = 0.0
    @State private var pulseAnimation = false
    
    var body: some View {
        ZStack {
            // 背景渐变
            LinearGradient(
                colors: [
                    Color(red: 0.01, green: 0.02, blue: 0.09),
                    Color(red: 0.06, green: 0.09, blue: 0.16)
                ],
                startPoint: .top,
                endPoint: .bottom
            )
            .ignoresSafeArea()
            
            // 顶部光晕
            RadialGradient(
                colors: [AppTheme.primary.opacity(0.16), .clear],
                center: .top,
                startRadius: 10,
                endRadius: 300
            )
            .ignoresSafeArea()
            
            VStack(spacing: 0) {
                // 顶部状态栏
                headerView
                
                // 消息列表
                messageListView
                
                // 底部操作栏
                bottomBarView
            }
        }
        .navigationBarHidden(true)
        .sheet(isPresented: $showTaskComposer) {
            taskComposerSheet
        }
    }
    
    // MARK: - 顶部头部
    
    private var headerView: some View {
        VStack(spacing: AppTheme.spacingSmall) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Callio")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(AppTheme.muted)
                        .textCase(.uppercase)
                        .tracking(1.2)
                    
                    Text("语音协作")
                        .font(.system(size: 22, weight: .bold))
                        .foregroundColor(AppTheme.text)
                }
                
                Spacer()
                
                // 连接状态
                statusPill
            }
            .padding(.horizontal, AppTheme.spacingXXL)
            .padding(.top, AppTheme.spacingLarge)
            .padding(.bottom, AppTheme.spacingMedium)
            
            Divider()
                .background(AppTheme.panelBorder)
        }
    }
    
    private var statusPill: some View {
        HStack(spacing: 6) {
            Image(systemName: appState.connectionStatus.icon)
                .font(.system(size: 12))
            
            Text(statusText)
                .font(.system(size: 13, weight: .medium))
        }
        .foregroundColor(appState.connectionStatus.color)
        .padding(.horizontal, AppTheme.spacingMedium)
        .padding(.vertical, 8)
        .background(
            Capsule()
                .fill(AppTheme.panelSoft)
        )
        .overlay(
            Capsule()
                .stroke(statusBorderColor, lineWidth: 1)
        )
        .scaleEffect(pulseAnimation && appState.isRecording ? 1.02 : 1)
        .animation(
            appState.isRecording
            ? .easeInOut(duration: 1.8).repeatForever(autoreverses: true)
            : .default,
            value: pulseAnimation
        )
        .onAppear {
            if appState.isRecording {
                pulseAnimation = true
            }
        }
        .onChange(of: appState.isRecording) { newValue in
            pulseAnimation = newValue
        }
    }
    
    private var statusText: String {
        switch appState.connectionStatus {
        case .disconnected: return "未连接"
        case .connecting: return "连接中..."
        case .connected: return "已连接"
        case .error: return "连接错误"
        }
    }
    
    private var statusBorderColor: Color {
        if appState.isRecording {
            return AppTheme.danger.opacity(0.5)
        }
        return appState.connectionStatus.color.opacity(0.3)
    }
    
    // MARK: - 消息列表
    
    private var messageListView: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: AppTheme.spacingMedium) {
                    if appState.messages.isEmpty {
                        emptyStateView
                    } else {
                        ForEach(appState.messages) { message in
                            MessageBubble(message: message)
                                .id(message.id)
                        }
                    }
                }
                .padding(.horizontal, AppTheme.spacingLarge)
                .padding(.vertical, AppTheme.spacingXL)
            }
            .onChange(of: appState.messages.count) { _ in
                scrollToBottom(proxy: proxy)
            }
            .onAppear {
                scrollProxy = proxy
            }
        }
    }
    
    private var emptyStateView: some View {
        VStack(spacing: AppTheme.spacingLarge) {
            Spacer()
                .frame(height: 80)
            
            // Logo / 图标
            ZStack {
                Circle()
                    .fill(AppTheme.primary.opacity(0.1))
                    .frame(width: 100, height: 100)
                
                Image(systemName: "waveform")
                    .font(.system(size: 40))
                    .foregroundColor(AppTheme.primary)
            }
            
            VStack(spacing: AppTheme.spacingSmall) {
                Text("开始语音对话")
                    .font(.system(size: 20, weight: .semibold))
                    .foregroundColor(AppTheme.text)
                
                Text("点击下方按钮，与 Callio 进行全双工语音交流")
                    .font(.system(size: 14))
                    .foregroundColor(AppTheme.muted)
                    .multilineTextAlignment(.center)
            }
            .padding(.horizontal, AppTheme.spacingXXL)
        }
    }
    
    private func scrollToBottom(proxy: ScrollViewProxy) {
        if let lastMessage = appState.messages.last {
            withAnimation(.easeOut(duration: 0.2)) {
                proxy.scrollTo(lastMessage.id, anchor: .bottom)
            }
        }
    }
    
    // MARK: - 底部操作栏
    
    private var bottomBarView: some View {
        VStack(spacing: AppTheme.spacingMedium) {
            // 状态提示
            if !appState.statusMessage.isEmpty {
                Text(appState.statusMessage)
                    .font(.system(size: 13))
                    .foregroundColor(AppTheme.muted)
                    .frame(maxWidth: .infinity, alignment: .center)
            }
            
            // 主操作按钮
            HStack(spacing: AppTheme.spacingLarge) {
                // 派发任务按钮
                Button {
                    showTaskComposer = true
                } label: {
                    Image(systemName: "plus.circle.fill")
                        .font(.system(size: 28))
                        .foregroundColor(AppTheme.primary)
                }
                .buttonStyle(.plain)
                
                Spacer()
                
                // 主语音按钮
                voiceButton
                
                Spacer()
                
                // 一键确认所有任务
                Button {
                    Task {
                        await appState.confirmAllTasks()
                    }
                } label: {
                    Image(systemName: "checkmark.circle.fill")
                        .font(.system(size: 28))
                        .foregroundColor(AppTheme.success)
                }
                .buttonStyle(.plain)
                .disabled(appState.tasks.isEmpty)
                .opacity(appState.tasks.isEmpty ? 0.4 : 1)
            }
            .padding(.horizontal, AppTheme.spacingXXL)
            .padding(.bottom, AppTheme.spacingLarge)
        }
        .padding(.top, AppTheme.spacingMedium)
        .background(
            AppTheme.panel
                .overlay(
                    Rectangle()
                        .fill(AppTheme.panelBorder)
                        .frame(height: 1),
                    alignment: .top
                )
        )
    }
    
    // 语音按钮
    private var voiceButton: some View {
        Button {
            if appState.isRecording {
                appState.stopVoiceSession()
            } else {
                appState.startVoiceSession()
            }
        } label: {
            ZStack {
                // 外圈脉冲
                if appState.isRecording {
                    Circle()
                        .fill(AppTheme.danger.opacity(0.3))
                        .frame(width: 80, height: 80)
                        .scaleEffect(pulseAnimation ? 1.3 : 1)
                        .opacity(pulseAnimation ? 0 : 1)
                        .animation(
                            .easeOut(duration: 1.5).repeatForever(autoreverses: false),
                            value: pulseAnimation
                        )
                }
                
                Circle()
                    .fill(
                        appState.isRecording
                        ? LinearGradient(
                            colors: [AppTheme.danger, Color(red: 0.88, green: 0.11, blue: 0.28)],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                        : LinearGradient(
                            colors: [AppTheme.primary, AppTheme.primaryStrong],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
                    .frame(width: 72, height: 72)
                    .shadow(color: (appState.isRecording ? AppTheme.danger : AppTheme.primary).opacity(0.4),
                            radius: 16, x: 0, y: 8)
                
                Image(systemName: appState.isRecording ? "stop.fill" : "mic.fill")
                    .font(.system(size: 30, weight: .medium))
                    .foregroundColor(.white)
            }
        }
        .buttonStyle(.plain)
        .scaleEffect(appState.isRecording ? 1 : 1)
    }
    
    // MARK: - 任务派发表单
    
    private var taskComposerSheet: some View {
        NavigationStack {
            ZStack {
                AppTheme.background.ignoresSafeArea()
                
                VStack(spacing: AppTheme.spacingLarge) {
                    // 标题输入
                    VStack(alignment: .leading, spacing: AppTheme.spacingSmall) {
                        Text("任务标题（可选）")
                            .font(.system(size: 13, weight: .medium))
                            .foregroundColor(AppTheme.muted)
                        
                        TextField("例如：整理需求清单", text: $taskTitle)
                            .textFieldStyle(.plain)
                            .padding()
                            .background(AppTheme.panelSoft)
                            .cornerRadius(AppTheme.cornerRadiusMedium)
                            .overlay(
                                RoundedRectangle(cornerRadius: AppTheme.cornerRadiusMedium)
                                    .stroke(AppTheme.panelBorder, lineWidth: 1)
                            )
                            .foregroundColor(AppTheme.text)
                    }
                    
                    // 描述输入
                    VStack(alignment: .leading, spacing: AppTheme.spacingSmall) {
                        Text("任务描述")
                            .font(.system(size: 13, weight: .medium))
                            .foregroundColor(AppTheme.muted)
                        
                        TextEditor(text: $taskDescription)
                            .scrollContentBackground(.hidden)
                            .padding()
                            .background(AppTheme.panelSoft)
                            .cornerRadius(AppTheme.cornerRadiusMedium)
                            .overlay(
                                RoundedRectangle(cornerRadius: AppTheme.cornerRadiusMedium)
                                    .stroke(AppTheme.panelBorder, lineWidth: 1)
                            )
                            .foregroundColor(AppTheme.text)
                            .frame(minHeight: 120)
                    }
                    
                    Spacer()
                    
                    // 派发按钮
                    Button {
                        Task {
                            isDispatching = true
                            await appState.dispatchTask(
                                title: taskTitle.isEmpty ? "手动任务" : taskTitle,
                                description: taskDescription
                            )
                            isDispatching = false
                            showTaskComposer = false
                            taskTitle = ""
                            taskDescription = ""
                        }
                    } label: {
                        Text("派发任务")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(PrimaryButtonStyle(isLoading: isDispatching))
                    .disabled(taskDescription.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    .opacity(taskDescription.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? 0.5 : 1)
                }
                .padding(AppTheme.spacingXXL)
            }
            .navigationTitle("派发任务")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("取消") {
                        showTaskComposer = false
                    }
                    .foregroundColor(AppTheme.primary)
                }
            }
        }
        .preferredColorScheme(.dark)
    }
}

// MARK: - 消息气泡

struct MessageBubble: View {
    let message: ChatMessage
    
    var body: some View {
        HStack(alignment: .top, spacing: AppTheme.spacingMedium) {
            if message.role == .user {
                Spacer()
            }
            
            if message.role != .user {
                // 头像
                Circle()
                    .fill(message.role.avatarColor.opacity(0.2))
                    .frame(width: 32, height: 32)
                    .overlay(
                        Image(systemName: message.role == .assistant ? "sparkles" : "exclamationmark.triangle")
                            .font(.system(size: 14))
                            .foregroundColor(message.role.avatarColor)
                    )
            }
            
            VStack(alignment: message.role == .user ? .trailing : .leading, spacing: 4) {
                Text("\(message.role.displayName) · \(message.timeString)")
                    .font(.system(size: 11))
                    .foregroundColor(AppTheme.muted)
                
                Text(message.text)
                    .font(.system(size: 15))
                    .foregroundColor(AppTheme.text)
                    .padding(.horizontal, AppTheme.spacingMedium)
                    .padding(.vertical, AppTheme.spacingSmall + 2)
                    .background(message.role.bubbleColor)
                    .cornerRadius(AppTheme.cornerRadiusLarge)
                    .overlay(
                        RoundedRectangle(cornerRadius: AppTheme.cornerRadiusLarge)
                            .stroke(message.role.borderColor, lineWidth: 1)
                    )
                
                if message.isStreaming {
                    HStack(spacing: 4) {
                        ForEach(0..<3) { i in
                            Circle()
                                .fill(AppTheme.muted)
                                .frame(width: 6, height: 6)
                                .opacity(0.5 + Double(i) * 0.25)
                                .scaleEffect(1.0 + CGFloat(i) * 0.2)
                        }
                    }
                    .padding(.top, 4)
                }
            }
            
            if message.role == .user {
                // 用户头像
                Circle()
                    .fill(message.role.avatarColor.opacity(0.2))
                    .frame(width: 32, height: 32)
                    .overlay(
                        Image(systemName: "person.fill")
                            .font(.system(size: 14))
                            .foregroundColor(message.role.avatarColor)
                    )
            }
            
            if message.role != .user {
                Spacer()
            }
        }
    }
}

struct ChatView_Previews: PreviewProvider {
    static var previews: some View {
        NavigationStack {
            ChatView()
        }
        .environmentObject(AppState())
        .preferredColorScheme(.dark)
    }
}

//
//  TaskListView.swift
//  Callio
//
//  任务列表视图
//

import SwiftUI

/// 任务列表视图
struct TaskListView: View {
    @EnvironmentObject var appState: AppState
    @State private var isRefreshing = false
    
    var body: some View {
        ZStack {
            AppTheme.background.ignoresSafeArea()
            
            VStack(spacing: 0) {
                // 标题栏
                headerView
                
                // 任务列表
                if appState.tasks.isEmpty {
                    emptyStateView
                } else {
                    taskListView
                }
            }
        }
        .navigationBarHidden(true)
        .onAppear {
            refreshTasks()
        }
    }
    
    // MARK: - 头部
    
    private var headerView: some View {
        VStack(spacing: AppTheme.spacingSmall) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("任务中心")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(AppTheme.muted)
                        .textCase(.uppercase)
                        .tracking(1.2)
                    
                    Text("后台任务")
                        .font(.system(size: 22, weight: .bold))
                        .foregroundColor(AppTheme.text)
                }
                
                Spacer()
                
                // 刷新按钮
                Button {
                    refreshTasks()
                } label: {
                    Image(systemName: "arrow.clockwise")
                        .font(.system(size: 18))
                        .foregroundColor(AppTheme.primary)
                        .rotationEffect(.degrees(isRefreshing ? 360 : 0))
                        .animation(isRefreshing ? .linear(duration: 1).repeatForever(autoreverses: false) : .default, value: isRefreshing)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, AppTheme.spacingXXL)
            .padding(.top, AppTheme.spacingLarge)
            .padding(.bottom, AppTheme.spacingMedium)
            
            // 统计信息
            if !appState.tasks.isEmpty {
                HStack(spacing: AppTheme.spacingMedium) {
                    PillView(text: "全部 \(appState.tasks.count)", kind: .default)
                    PillView(text: "运行中 \(runningCount)", kind: .info)
                    PillView(text: "待确认 \(pendingCount)", kind: .warning)
                    PillView(text: "已完成 \(completedCount)", kind: .success)
                }
                .padding(.horizontal, AppTheme.spacingXXL)
                .padding(.bottom, AppTheme.spacingMedium)
            }
            
            Divider()
                .background(AppTheme.panelBorder)
        }
    }
    
    private var runningCount: Int {
        appState.tasks.filter { $0.status == .running }.count
    }
    
    private var pendingCount: Int {
        appState.tasks.filter { $0.status == .proposed || $0.status == .pending }.count
    }
    
    private var completedCount: Int {
        appState.tasks.filter { $0.status == .completed || $0.status == .success }.count
    }
    
    // MARK: - 空状态
    
    private var emptyStateView: some View {
        VStack(spacing: AppTheme.spacingLarge) {
            Spacer()
            
            ZStack {
                Circle()
                    .fill(AppTheme.primary.opacity(0.1))
                    .frame(width: 100, height: 100)
                
                Image(systemName: "list.bullet.rectangle")
                    .font(.system(size: 40))
                    .foregroundColor(AppTheme.primary)
            }
            
            VStack(spacing: AppTheme.spacingSmall) {
                Text("暂无任务")
                    .font(.system(size: 20, weight: .semibold))
                    .foregroundColor(AppTheme.text)
                
                Text("开始语音对话或手动派发任务后，任务将显示在这里")
                    .font(.system(size: 14))
                    .foregroundColor(AppTheme.muted)
                    .multilineTextAlignment(.center)
            }
            .padding(.horizontal, AppTheme.spacingXXL)
            
            Spacer()
        }
    }
    
    // MARK: - 任务列表
    
    private var taskListView: some View {
        ScrollView {
            LazyVStack(spacing: AppTheme.spacingMedium) {
                ForEach(appState.tasks) { task in
                    TaskCard(task: task) { action in
                        handleTaskAction(action, for: task)
                    }
                }
            }
            .padding(.horizontal, AppTheme.spacingLarge)
            .padding(.vertical, AppTheme.spacingXL)
        }
    }
    
    // MARK: - 操作
    
    private func refreshTasks() {
        isRefreshing = true
        
        let sessionId = appState.currentSessionId ?? appState.selectedSessionId
        
        Task {
            if let sid = sessionId {
                await appState.loadSessionTasks(sessionId: sid)
            }
            isRefreshing = false
        }
    }
    
    private func handleTaskAction(_ action: TaskAction, for task: TaskItem) {
        Task {
            switch action {
            case .confirm:
                await appState.confirmTask(nodeId: task.nodeId)
            case .cancel:
                await appState.cancelTask(nodeId: task.nodeId)
            case .stop:
                await appState.cancelTask(nodeId: task.nodeId)
            }
        }
    }
}

// MARK: - 任务卡片

enum TaskAction {
    case confirm
    case cancel
    case stop
}

struct TaskCard: View {
    let task: TaskItem
    var onAction: ((TaskAction) -> Void)?
    
    var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.spacingMedium) {
            // 头部
            HStack(alignment: .top, spacing: AppTheme.spacingMedium) {
                // 状态图标
                Image(systemName: task.status.icon)
                    .font(.system(size: 20))
                    .foregroundColor(task.status.color)
                    .frame(width: 24)
                    .padding(.top, 2)
                
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: AppTheme.spacingSmall) {
                        Text(task.title)
                            .font(.system(size: 15, weight: .semibold))
                            .foregroundColor(AppTheme.text)
                            .lineLimit(2)
                        
                        Spacer()
                        
                        if let kind = task.kind {
                            kindBadge(kind)
                        }
                    }
                    
                    HStack(spacing: 6) {
                        Text(task.status.displayName)
                            .font(.system(size: 12))
                            .foregroundColor(task.status.color)
                        
                        if let progress = task.progress {
                            Text("· \(Int(progress))%")
                                .font(.system(size: 12))
                                .foregroundColor(AppTheme.muted)
                        }
                    }
                }
            }
            
            // 描述
            if let description = task.description, !description.isEmpty {
                Text(description)
                    .font(.system(size: 13))
                    .foregroundColor(AppTheme.muted)
                    .lineLimit(2)
                    .padding(.leading, 32)
            }
            
            // 进度条
            if let progress = task.progress {
                ProgressView(value: progress / 100)
                    .progressViewStyle(LinearProgressViewStyle(tint: AppTheme.primary))
                    .padding(.leading, 32)
            }
            
            // 结果预览
            if let result = task.resultSummary, !result.isEmpty {
                HStack(spacing: 0) {
                    Rectangle()
                        .fill(AppTheme.success.opacity(0.4))
                        .frame(width: 3)
                    
                    Text(result)
                        .font(.system(size: 12))
                        .foregroundColor(AppTheme.muted)
                        .lineLimit(3)
                        .padding(.leading, AppTheme.spacingSmall)
                        .padding(.vertical, 6)
                    
                    Spacer()
                }
                .background(AppTheme.muted.opacity(0.07))
                .cornerRadius(6)
                .padding(.leading, 32)
            }
            
            // 操作按钮
            if let actions = availableActions, !actions.isEmpty {
                HStack(spacing: AppTheme.spacingSmall) {
                    ForEach(actions, id: \.self) { action in
                        Button {
                            onAction?(action)
                        } label: {
                            Text(actionTitle(action))
                                .font(.system(size: 13, weight: .medium))
                                .foregroundColor(actionColor(action))
                                .padding(.horizontal, AppTheme.spacingMedium)
                                .padding(.vertical, 8)
                                .background(actionBackground(action))
                                .cornerRadius(AppTheme.cornerRadiusSmall)
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.leading, 32)
            }
        }
        .padding(AppTheme.spacingLarge)
        .background(AppTheme.panel)
        .cornerRadius(AppTheme.cornerRadiusLarge)
        .overlay(
            RoundedRectangle(cornerRadius: AppTheme.cornerRadiusLarge)
                .stroke(task.status.borderColor, lineWidth: 1)
        )
    }
    
    private var availableActions: [TaskAction]? {
        switch task.status {
        case .proposed, .pending:
            return [.confirm, .cancel]
        case .running:
            return [.stop]
        default:
            return nil
        }
    }
    
    private func actionTitle(_ action: TaskAction) -> String {
        switch action {
        case .confirm: return "确认"
        case .cancel: return "取消"
        case .stop: return "停止"
        }
    }
    
    private func actionColor(_ action: TaskAction) -> Color {
        switch action {
        case .confirm: return .white
        case .cancel: return AppTheme.text
        case .stop: return .white
        }
    }
    
    private func actionBackground(_ action: TaskAction) -> Color {
        switch action {
        case .confirm: return AppTheme.primary
        case .cancel: return AppTheme.panelSoft
        case .stop: return AppTheme.danger
        }
    }
    
    private func kindBadge(_ kind: TaskKind) -> some View {
        Text(kind.displayName)
            .font(.system(size: 10, weight: .semibold))
            .foregroundColor(kind.color)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(kind.color.opacity(0.15))
            .cornerRadius(4)
            .overlay(
                RoundedRectangle(cornerRadius: 4)
                    .stroke(kind.color.opacity(0.4), lineWidth: 0.5)
            )
    }
}

struct TaskListView_Previews: PreviewProvider {
    static var previews: some View {
        NavigationStack {
            TaskListView()
        }
        .environmentObject(AppState())
        .preferredColorScheme(.dark)
    }
}

//
//  SessionListView.swift
//  Callio
//
//  会话历史视图
//

import SwiftUI

/// 会话列表视图
struct SessionListView: View {
    @EnvironmentObject var appState: AppState
    @State private var isRefreshing = false
    @State private var showClearConfirm = false
    
    var body: some View {
        ZStack {
            AppTheme.background.ignoresSafeArea()
            
            VStack(spacing: 0) {
                // 标题栏
                headerView
                
                // 会话列表
                if appState.sessions.isEmpty {
                    emptyStateView
                } else {
                    sessionListView
                }
            }
        }
        .navigationBarHidden(true)
        .alert("清除历史", isPresented: $showClearConfirm) {
            Button("取消", role: .cancel) { }
            Button("清除", role: .destructive) {
                clearSessions()
            }
        } message: {
            Text("确定要清除所有保存的会话和任务历史吗？此操作不可撤销。")
        }
        .onAppear {
            refreshSessions()
        }
    }
    
    // MARK: - 头部
    
    private var headerView: some View {
        VStack(spacing: AppTheme.spacingSmall) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("会话历史")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(AppTheme.muted)
                        .textCase(.uppercase)
                        .tracking(1.2)
                    
                    Text("历史记录")
                        .font(.system(size: 22, weight: .bold))
                        .foregroundColor(AppTheme.text)
                }
                
                Spacer()
                
                HStack(spacing: AppTheme.spacingMedium) {
                    // 清除按钮
                    Button {
                        showClearConfirm = true
                    } label: {
                        Image(systemName: "trash")
                            .font(.system(size: 18))
                            .foregroundColor(AppTheme.danger)
                    }
                    .buttonStyle(.plain)
                    .disabled(appState.sessions.isEmpty)
                    .opacity(appState.sessions.isEmpty ? 0.4 : 1)
                    
                    // 刷新按钮
                    Button {
                        refreshSessions()
                    } label: {
                        Image(systemName: "arrow.clockwise")
                            .font(.system(size: 18))
                            .foregroundColor(AppTheme.primary)
                            .rotationEffect(.degrees(isRefreshing ? 360 : 0))
                            .animation(isRefreshing ? .linear(duration: 1).repeatForever(autoreverses: false) : .default, value: isRefreshing)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, AppTheme.spacingXXL)
            .padding(.top, AppTheme.spacingLarge)
            .padding(.bottom, AppTheme.spacingMedium)
            
            // 当前选中会话
            if let selectedId = appState.selectedSessionId,
               let session = appState.sessions.first(where: { $0.sessionId == selectedId }) {
                HStack(spacing: AppTheme.spacingSmall) {
                    Image(systemName: "target")
                        .font(.system(size: 12))
                        .foregroundColor(AppTheme.primary)
                    
                    Text("目标会话: \(session.displayTitle)")
                        .font(.system(size: 13))
                        .foregroundColor(AppTheme.primary)
                    
                    Spacer()
                    
                    Button {
                        appState.selectedSessionId = nil
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .font(.system(size: 14))
                            .foregroundColor(AppTheme.muted)
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, AppTheme.spacingXXL)
                .padding(.bottom, AppTheme.spacingMedium)
            }
            
            Divider()
                .background(AppTheme.panelBorder)
        }
    }
    
    // MARK: - 空状态
    
    private var emptyStateView: some View {
        VStack(spacing: AppTheme.spacingLarge) {
            Spacer()
            
            ZStack {
                Circle()
                    .fill(AppTheme.primary.opacity(0.1))
                    .frame(width: 100, height: 100)
                
                Image(systemName: "clock.arrow.circlepath")
                    .font(.system(size: 40))
                    .foregroundColor(AppTheme.primary)
            }
            
            VStack(spacing: AppTheme.spacingSmall) {
                Text("暂无历史会话")
                    .font(.system(size: 20, weight: .semibold))
                    .foregroundColor(AppTheme.text)
                
                Text("开始语音对话后，会话记录将保存在这里")
                    .font(.system(size: 14))
                    .foregroundColor(AppTheme.muted)
                    .multilineTextAlignment(.center)
            }
            .padding(.horizontal, AppTheme.spacingXXL)
            
            Spacer()
        }
    }
    
    // MARK: - 会话列表
    
    private var sessionListView: some View {
        ScrollView {
            LazyVStack(spacing: AppTheme.spacingMedium) {
                ForEach(appState.sessions) { session in
                    SessionRow(
                        session: session,
                        isSelected: appState.selectedSessionId == session.sessionId
                    ) {
                        appState.selectSession(session)
                        // 加载该会话的任务
                        Task {
                            await appState.loadSessionTasks(sessionId: session.sessionId)
                        }
                    }
                }
            }
            .padding(.horizontal, AppTheme.spacingLarge)
            .padding(.vertical, AppTheme.spacingXL)
        }
    }
    
    // MARK: - 操作
    
    private func refreshSessions() {
        isRefreshing = true
        Task {
            await appState.loadSessions()
            isRefreshing = false
        }
    }
    
    private func clearSessions() {
        Task {
            do {
                _ = try await appState.apiService.clearAllSessions()
                appState.selectedSessionId = nil
                await appState.loadSessions()
            } catch {
                appState.errorMessage = "清除历史失败: \(error.localizedDescription)"
                appState.showError = true
            }
        }
    }
}

// MARK: - 会话行

struct SessionRow: View {
    let session: Session
    let isSelected: Bool
    var onTap: (() -> Void)?
    
    var body: some View {
        Button {
            onTap?()
        } label: {
            HStack(spacing: AppTheme.spacingMedium) {
                // 图标
                ZStack {
                    Circle()
                        .fill(iconBackground)
                        .frame(width: 44, height: 44)
                    
                    Image(systemName: session.isActive ? "phone.connection" : "clock")
                        .font(.system(size: 18))
                        .foregroundColor(iconColor)
                }
                
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text(session.displayTitle)
                            .font(.system(size: 15, weight: .semibold))
                            .foregroundColor(AppTheme.text)
                            .lineLimit(1)
                        
                        Spacer()
                        
                        if isSelected {
                            Image(systemName: "checkmark.circle.fill")
                                .foregroundColor(AppTheme.primary)
                                .font(.system(size: 16))
                        }
                    }
                    
                    HStack(spacing: 6) {
                        Text(session.shortId)
                            .font(.system(size: 12))
                            .foregroundColor(AppTheme.muted)
                        
                        Text("·")
                            .font(.system(size: 12))
                            .foregroundColor(AppTheme.muted)
                        
                        Text(session.statusText)
                            .font(.system(size: 12))
                            .foregroundColor(session.isActive ? AppTheme.success : AppTheme.muted)
                    }
                    
                    if let summary = session.summary, !summary.isEmpty {
                        Text(summary)
                            .font(.system(size: 12))
                            .foregroundColor(AppTheme.muted)
                            .lineLimit(2)
                            .padding(.top, 2)
                    }
                }
            }
            .padding(AppTheme.spacingLarge)
            .background(isSelected ? AppTheme.primary.opacity(0.12) : AppTheme.panel)
            .cornerRadius(AppTheme.cornerRadiusLarge)
            .overlay(
                RoundedRectangle(cornerRadius: AppTheme.cornerRadiusLarge)
                    .stroke(isSelected ? AppTheme.primary.opacity(0.5) : AppTheme.panelBorder, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
    }
    
    private var iconBackground: Color {
        session.isActive
        ? AppTheme.success.opacity(0.15)
        : AppTheme.muted.opacity(0.1)
    }
    
    private var iconColor: Color {
        session.isActive ? AppTheme.success : AppTheme.muted
    }
}

struct SessionListView_Previews: PreviewProvider {
    static var previews: some View {
        NavigationStack {
            SessionListView()
        }
        .environmentObject(AppState())
        .preferredColorScheme(.dark)
    }
}

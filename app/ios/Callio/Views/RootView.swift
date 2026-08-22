//
//  RootView.swift
//  Callio
//
//  主视图 - 底部标签导航
//

import SwiftUI

/// 主视图
struct RootView: View {
    @EnvironmentObject var appState: AppState
    @State private var selectedTab: Tab = .chat
    
    enum Tab: String, CaseIterable {
        case chat = "对话"
        case tasks = "任务"
        case sessions = "会话"
        case settings = "设置"
        
        var icon: String {
            switch self {
            case .chat: return "message.fill"
            case .tasks: return "list.bullet.rectangle.fill"
            case .sessions: return "clock.arrow.circlepath"
            case .settings: return "gearshape.fill"
            }
        }
    }
    
    var body: some View {
        TabView(selection: $selectedTab) {
            NavigationStack {
                ChatView()
            }
            .tabItem {
                Label(Tab.chat.rawValue, systemImage: Tab.chat.icon)
            }
            .tag(Tab.chat)
            
            NavigationStack {
                TaskListView()
            }
            .tabItem {
                Label(Tab.tasks.rawValue, systemImage: Tab.tasks.icon)
            }
            .tag(Tab.tasks)
            
            NavigationStack {
                SessionListView()
            }
            .tabItem {
                Label(Tab.sessions.rawValue, systemImage: Tab.sessions.icon)
            }
            .tag(Tab.sessions)
            
            NavigationStack {
                SettingsView()
            }
            .tabItem {
                Label(Tab.settings.rawValue, systemImage: Tab.settings.icon)
            }
            .tag(Tab.settings)
        }
        .tint(AppTheme.primary)
        .alert("错误", isPresented: $appState.showError) {
            Button("确定", role: .cancel) { }
        } message: {
            Text(appState.errorMessage ?? "未知错误")
        }
        .onAppear {
            // 加载会话列表
            Task {
                await appState.loadSessions()
            }
        }
    }
}

// MARK: - 应用主题

enum AppTheme {
    // 主色调
    static let primary = Color(red: 0.38, green: 0.65, blue: 0.98)
    static let primaryStrong = Color(red: 0.23, green: 0.51, blue: 0.96)
    static let success = Color(red: 0.21, green: 0.83, blue: 0.60)
    static let warning = Color(red: 0.98, green: 0.75, blue: 0.14)
    static let danger = Color(red: 0.98, green: 0.44, blue: 0.52)
    
    // 背景色
    static let background = Color(red: 0.04, green: 0.06, blue: 0.14)
    static let panel = Color(red: 0.06, green: 0.09, blue: 0.16).opacity(0.9)
    static let panelSoft = Color(red: 0.06, green: 0.09, blue: 0.16).opacity(0.72)
    static let panelBorder = Color(red: 0.58, green: 0.64, blue: 0.72).opacity(0.18)
    
    // 文本色
    static let text = Color(red: 0.90, green: 0.93, blue: 0.98)
    static let muted = Color(red: 0.58, green: 0.64, blue: 0.72)
    
    // 圆角
    static let cornerRadiusSmall: CGFloat = 12
    static let cornerRadiusMedium: CGFloat = 16
    static let cornerRadiusLarge: CGFloat = 22
    static let cornerRadiusXL: CGFloat = 28
    
    // 间距
    static let spacingSmall: CGFloat = 8
    static let spacingMedium: CGFloat = 12
    static let spacingLarge: CGFloat = 16
    static let spacingXL: CGFloat = 20
    static let spacingXXL: CGFloat = 24
}

// MARK: - 按钮样式

struct PrimaryButtonStyle: ButtonStyle {
    var isLoading: Bool = false
    
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 16, weight: .semibold))
            .foregroundColor(.white)
            .padding(.horizontal, AppTheme.spacingLarge)
            .padding(.vertical, AppTheme.spacingMedium)
            .background(
                LinearGradient(
                    colors: [AppTheme.primary, AppTheme.primaryStrong],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            )
            .cornerRadius(AppTheme.cornerRadiusMedium)
            .scaleEffect(configuration.isPressed ? 0.97 : 1)
            .opacity(isLoading ? 0.7 : 1)
            .overlay {
                if isLoading {
                    ProgressView()
                        .tint(.white)
                }
            }
    }
}

struct DangerButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 16, weight: .semibold))
            .foregroundColor(.white)
            .padding(.horizontal, AppTheme.spacingLarge)
            .padding(.vertical, AppTheme.spacingMedium)
            .background(
                LinearGradient(
                    colors: [AppTheme.danger, Color(red: 0.88, green: 0.11, blue: 0.28)],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            )
            .cornerRadius(AppTheme.cornerRadiusMedium)
            .scaleEffect(configuration.isPressed ? 0.97 : 1)
    }
}

struct GhostButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 14, weight: .medium))
            .foregroundColor(AppTheme.text)
            .padding(.horizontal, AppTheme.spacingMedium)
            .padding(.vertical, 10)
            .background(AppTheme.panelSoft)
            .cornerRadius(AppTheme.cornerRadiusMedium)
            .overlay(
                RoundedRectangle(cornerRadius: AppTheme.cornerRadiusMedium)
                    .stroke(AppTheme.panelBorder, lineWidth: 1)
            )
            .scaleEffect(configuration.isPressed ? 0.97 : 1)
    }
}

// MARK: - 胶囊标签

struct PillView: View {
    let text: String
    var kind: PillKind = .default
    
    enum PillKind {
        case `default`
        case success
        case warning
        case danger
        case info
    }
    
    var body: some View {
        Text(text)
            .font(.system(size: 13, weight: .medium))
            .foregroundColor(textColor)
            .padding(.horizontal, AppTheme.spacingMedium)
            .padding(.vertical, 8)
            .background(
                Capsule()
                    .fill(AppTheme.panelSoft)
            )
            .overlay(
                Capsule()
                    .stroke(borderColor, lineWidth: 1)
            )
    }
    
    private var textColor: Color {
        switch kind {
        case .default: return AppTheme.text
        case .success: return AppTheme.success
        case .warning: return AppTheme.warning
        case .danger: return AppTheme.danger
        case .info: return AppTheme.primary
        }
    }
    
    private var borderColor: Color {
        switch kind {
        case .default: return AppTheme.panelBorder
        case .success: return AppTheme.success.opacity(0.3)
        case .warning: return AppTheme.warning.opacity(0.3)
        case .danger: return AppTheme.danger.opacity(0.3)
        case .info: return AppTheme.primary.opacity(0.3)
        }
    }
}

// MARK: - 预览

struct RootView_Previews: PreviewProvider {
    static var previews: some View {
        RootView()
            .environmentObject(AppState())
            .preferredColorScheme(.dark)
    }
}

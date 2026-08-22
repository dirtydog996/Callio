//
//  ChatMessage.swift
//  Callio
//
//  聊天消息数据模型
//

import Foundation
import SwiftUI

/// 消息角色
enum ChatRole: String, Codable {
    case user
    case assistant
    case error
    case system
    
    var displayName: String {
        switch self {
        case .user: return "你"
        case .assistant: return "Callio"
        case .error: return "错误"
        case .system: return "系统"
        }
    }
    
    var avatarColor: Color {
        switch self {
        case .user: return Color(red: 0.37, green: 0.65, blue: 0.98)
        case .assistant: return Color(red: 0.21, green: 0.83, blue: 0.60)
        case .error: return Color(red: 0.98, green: 0.44, blue: 0.52)
        case .system: return Color.gray
        }
    }
    
    var bubbleColor: Color {
        switch self {
        case .user:
            return Color(red: 0.23, green: 0.51, blue: 0.96).opacity(0.18)
        case .assistant:
            return Color(red: 0.06, green: 0.09, blue: 0.16).opacity(0.88)
        case .error:
            return Color(red: 0.50, green: 0.11, blue: 0.11).opacity(0.22)
        case .system:
            return Color.gray.opacity(0.2)
        }
    }
    
    var borderColor: Color {
        switch self {
        case .user:
            return Color(red: 0.38, green: 0.65, blue: 0.98).opacity(0.22)
        case .assistant:
            return Color(red: 0.58, green: 0.64, blue: 0.72).opacity(0.14)
        case .error:
            return Color(red: 0.98, green: 0.44, blue: 0.52).opacity(0.32)
        case .system:
            return Color.gray.opacity(0.3)
        }
    }
}

/// 聊天消息
struct ChatMessage: Identifiable, Equatable {
    let id: UUID
    let role: ChatRole
    var text: String
    let timestamp: Date
    var isStreaming: Bool = false
    
    var timeString: String {
        let formatter = DateFormatter()
        formatter.dateFormat = "HH:mm"
        return formatter.string(from: timestamp)
    }
}

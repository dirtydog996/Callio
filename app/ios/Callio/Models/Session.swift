//
//  Session.swift
//  Callio
//
//  会话数据模型
//

import Foundation

/// 会话模型
struct Session: Identifiable, Codable, Equatable {
    let sessionId: String
    let title: String?
    let summary: String?
    let transcript: String?
    let createdAt: Date?
    let endedAt: Date?
    
    var id: String { sessionId }
    
    var isActive: Bool { endedAt == nil }
    
    var displayTitle: String {
        title ?? String(sessionId.prefix(8))
    }
    
    var statusText: String {
        isActive ? "进行中" : "已结束"
    }
    
    var shortId: String {
        String(sessionId.prefix(8))
    }
    
    enum CodingKeys: String, CodingKey {
        case sessionId = "session_id"
        case title
        case summary
        case transcript
        case createdAt = "created_at"
        case endedAt = "ended_at"
    }
}

/// 会话列表响应
struct SessionsResponse: Codable {
    let items: [Session]
}

/// 会话详情响应
struct SessionDetailResponse: Codable {
    let found: Bool
    let session: Session?
}

/// 任务列表响应
struct TasksResponse: Codable {
    let tasks: [TaskData]
    let events: [TaskEvent]?
}

/// 任务数据
struct TaskData: Codable {
    let nodeId: String
    let featureName: String?
    let description: String?
    let status: String?
    let phase: String?
    let kind: String?
    
    enum CodingKeys: String, CodingKey {
        case nodeId = "node_id"
        case featureName = "feature_name"
        case description
        case status
        case phase
        case kind
    }
}

//
//  TaskItem.swift
//  Callio
//
//  任务数据模型
//

import Foundation
import SwiftUI

/// 任务状态
enum TaskStatus: String, Codable {
    case proposed = "PROPOSED"
    case pending = "PENDING"
    case confirmed = "CONFIRMED"
    case running = "RUNNING"
    case completed = "COMPLETED"
    case success = "SUCCESS"
    case failed = "FAILED"
    case cancelled = "CANCELLED"
    
    var displayName: String {
        switch self {
        case .proposed: return "待确认"
        case .pending: return "等待确认"
        case .confirmed: return "等待执行"
        case .running: return "运行中"
        case .completed, .success: return "已完成"
        case .failed: return "失败"
        case .cancelled: return "已取消"
        }
    }
    
    var icon: String {
        switch self {
        case .proposed, .pending, .confirmed: return "circle.dashed"
        case .running: return "arrow.triangle.2.circlepath"
        case .completed, .success: return "checkmark.circle.fill"
        case .failed: return "xmark.circle.fill"
        case .cancelled: return "slash.circle"
        }
    }
    
    var color: Color {
        switch self {
        case .proposed, .pending: return .yellow
        case .confirmed: return .blue
        case .running: return .blue
        case .completed, .success: return .green
        case .failed: return .red
        case .cancelled: return .gray
        }
    }
    
    var borderColor: Color {
        switch self {
        case .proposed, .pending: return Color.yellow.opacity(0.3)
        case .confirmed, .running: return Color.blue.opacity(0.3)
        case .completed, .success: return Color.green.opacity(0.32)
        case .failed, .cancelled: return Color.red.opacity(0.28)
        }
    }
}

/// 任务类型
enum TaskKind: String, Codable {
    case analyze = "ANALYZE"
    case execute = "EXECUTE"
    case summarize = "SUMMARIZE"
    
    var displayName: String {
        switch self {
        case .analyze: return "分析"
        case .execute: return "执行"
        case .summarize: return "总结"
        }
    }
    
    var color: Color {
        switch self {
        case .analyze: return Color(red: 0.38, green: 0.65, blue: 0.98)
        case .execute: return Color(red: 0.98, green: 0.75, blue: 0.14)
        case .summarize: return Color(red: 0.21, green: 0.83, blue: 0.60)
        }
    }
}

/// 任务项
struct TaskItem: Identifiable, Equatable {
    let id: UUID
    let nodeId: String
    var title: String
    var description: String?
    var status: TaskStatus
    var kind: TaskKind?
    var progress: Double?
    var resultSummary: String?
    var phase: String?
    
    init(id: UUID = UUID(), nodeId: String, title: String, description: String? = nil,
         status: TaskStatus, kind: TaskKind? = nil, progress: Double? = nil,
         resultSummary: String? = nil, phase: String? = nil) {
        self.id = id
        self.nodeId = nodeId
        self.title = title
        self.description = description
        self.status = status
        self.kind = kind
        self.progress = progress
        self.resultSummary = resultSummary
        self.phase = phase
    }
    
    init(from event: TaskEvent) {
        self.id = UUID()
        self.nodeId = event.nodeId ?? "\(event.event)-\(Date().timeIntervalSince1970)"
        self.title = event.featureName ?? event.title ?? event.nodeId ?? "任务"
        self.status = TaskStatus(rawValue: event.status ?? event.phase ?? event.event) ?? .pending
        self.kind = TaskKind(rawValue: event.kind ?? "")
        self.progress = event.progress
        self.resultSummary = event.resultSummary ?? event.report
        self.phase = event.phase
    }
    
    mutating func update(with event: TaskEvent) {
        if let newTitle = event.featureName ?? event.title {
            self.title = newTitle
        }
        if let statusStr = event.status ?? event.phase,
           let newStatus = TaskStatus(rawValue: statusStr) {
            self.status = newStatus
        }
        if let kindStr = event.kind, let newKind = TaskKind(rawValue: kindStr) {
            self.kind = newKind
        }
        if let newProgress = event.progress {
            self.progress = newProgress
        }
        if let summary = event.resultSummary ?? event.report {
            self.resultSummary = summary
        }
    }
}

/// 任务事件（来自WebSocket）
struct TaskEvent: Codable {
    let event: String
    let nodeId: String?
    let featureName: String?
    let title: String?
    let status: String?
    let phase: String?
    let kind: String?
    let progress: Double?
    let resultSummary: String?
    let report: String?
    let sessionId: String?
    
    enum CodingKeys: String, CodingKey {
        case event
        case nodeId = "node_id"
        case featureName = "feature_name"
        case title
        case status
        case phase
        case kind
        case progress
        case resultSummary = "result_summary"
        case report
        case sessionId = "session_id"
    }
}

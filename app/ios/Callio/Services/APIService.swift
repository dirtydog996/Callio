//
//  APIService.swift
//  Callio
//
//  REST API 服务
//

import Foundation

/// API 服务
final class APIService {
    // MARK: - 属性
    private var baseURL: String {
        let host = UserDefaults.standard.string(forKey: "serverHost") ?? "localhost"
        let port = UserDefaults.standard.string(forKey: "serverPort") ?? "8000"
        let useHTTPS = UserDefaults.standard.bool(forKey: "useHTTPS")
        let scheme = useHTTPS ? "https" : "http"
        return "\(scheme)://\(host):\(port)/api/v1"
    }
    
    // MARK: - 通用请求方法
    
    private func request<T: Decodable>(_ path: String, method: String = "GET", body: [String: Any]? = nil) async throws -> T {
        let urlString = "\(baseURL)\(path)"
        guard let url = URL(string: urlString) else {
            throw APIError.invalidURL
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        if let body = body {
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
        }
        
        let (data, response) = try await URLSession.shared.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }
        
        guard (200...299).contains(httpResponse.statusCode) else {
            let errorText = String(data: data, encoding: .utf8) ?? "未知错误"
            throw APIError.serverError(statusCode: httpResponse.statusCode, message: errorText)
        }
        
        do {
            let decoder = JSONDecoder()
            decoder.dateDecodingStrategy = .iso8601
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            return try decoder.decode(T.self, from: data)
        } catch {
            print("JSON 解码失败: \(error)")
            throw APIError.decodingError(error)
        }
    }
    
    // MARK: - 会话相关
    
    /// 获取会话列表
    func fetchSessions() async throws -> [Session] {
        let response: SessionsResponse = try await request("/sessions")
        return response.items
    }
    
    /// 获取会话详情
    func fetchSessionDetail(sessionId: String) async throws -> Session? {
        let encodedId = sessionId.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? sessionId
        let response: SessionDetailResponse = try await request("/sessions/\(encodedId)")
        return response.session
    }
    
    /// 清除所有会话
    func clearAllSessions() async throws -> [String: Int] {
        struct ClearResponse: Decodable {
            let counts: [String: Int]?
        }
        let response: ClearResponse = try await request("/sessions", method: "DELETE")
        return response.counts ?? [:]
    }
    
    // MARK: - 任务相关
    
    /// 获取会话任务列表
    func fetchTasks(sessionId: String) async throws -> [TaskItem] {
        let encodedId = sessionId.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? sessionId
        let response: TasksResponse = try await request("/sessions/\(encodedId)/tasks")
        
        var tasks: [TaskItem] = []
        
        // 从 tasks 数组转换
        for taskData in response.tasks {
            let status = TaskStatus(rawValue: taskData.status ?? taskData.phase ?? "") ?? .pending
            let kind = TaskKind(rawValue: taskData.kind ?? "")
            tasks.append(TaskItem(
                nodeId: taskData.nodeId,
                title: taskData.featureName ?? taskData.nodeId,
                description: taskData.description,
                status: status,
                kind: kind
            ))
        }
        
        // 从 events 数组转换
        if let events = response.events {
            for event in events {
                tasks.append(TaskItem(from: event))
            }
        }
        
        return tasks
    }
    
    /// 派发手动任务
    func dispatchTask(title: String, description: String, sessionId: String?) async throws -> [String: String] {
        var body: [String: Any] = [
            "feature_name": title,
            "description": description,
            "difficulty_level": 1
        ]
        if let sessionId = sessionId {
            body["session_id"] = sessionId
        }
        
        struct DispatchResponse: Decodable {
            let nodeId: String
            let message: String?
        }
        
        let response: DispatchResponse = try await request("/tasks/dispatch", method: "POST", body: body)
        return ["node_id": response.nodeId, "message": response.message ?? ""]
    }
    
    /// 确认任务
    func confirmTask(sessionId: String, nodeIds: [String], confirmAll: Bool = false) async throws -> [String: String] {
        let encodedId = sessionId.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? sessionId
        let body: [String: Any] = [
            "node_ids": nodeIds,
            "confirm_all": confirmAll
        ]
        
        struct ConfirmResponse: Decodable {
            let message: String?
        }
        
        let response: ConfirmResponse = try await request("/sessions/\(encodedId)/tasks/confirm", method: "POST", body: body)
        return ["message": response.message ?? "已确认"]
    }
    
    /// 取消任务
    func cancelTask(sessionId: String, nodeIds: [String]) async throws -> [String: String] {
        let encodedId = sessionId.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? sessionId
        let body: [String: Any] = [
            "node_ids": nodeIds
        ]
        
        struct CancelResponse: Decodable {
            let message: String?
        }
        
        let response: CancelResponse = try await request("/sessions/\(encodedId)/tasks/cancel", method: "POST", body: body)
        return ["message": response.message ?? "已取消"]
    }
    
    /// 取消运行中的任务
    func cancelRunningTask(nodeId: String) async throws -> [String: String] {
        let encodedId = nodeId.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? nodeId
        
        struct CancelResponse: Decodable {
            let message: String?
        }
        
        let response: CancelResponse = try await request("/tasks/\(encodedId)/cancel", method: "POST")
        return ["message": response.message ?? "已请求停止"]
    }
    
    // MARK: - 设置相关
    
    /// 获取当前设置
    func fetchSettings() async throws -> [String: String] {
        struct SettingsResponse: Decodable {
            let settings: [String: String]
            let configured: Bool
        }
        
        let response: SettingsResponse = try await request("/settings")
        return response.settings
    }
    
    /// 保存设置
    func saveSettings(_ settings: [String: String]) async throws -> Bool {
        let body = ["settings": settings]
        
        struct SaveResponse: Decodable {
            let configured: Bool
            let missing: [String]?
        }
        
        let response: SaveResponse = try await request("/settings", method: "PUT", body: body)
        return response.configured
    }
}

// MARK: - 错误类型

enum APIError: LocalizedError {
    case invalidURL
    case invalidResponse
    case serverError(statusCode: Int, message: String)
    case decodingError(Error)
    
    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "无效的服务器地址"
        case .invalidResponse:
            return "无效的服务器响应"
        case .serverError(let statusCode, let message):
            return "服务器错误 (\(statusCode)): \(message)"
        case .decodingError(let error):
            return "数据解析失败: \(error.localizedDescription)"
        }
    }
}

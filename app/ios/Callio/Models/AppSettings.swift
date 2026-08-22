//
//  AppSettings.swift
//  Callio
//
//  应用设置模型
//

import Foundation

/// LLM 提供商
enum LLMProvider: String, Codable, CaseIterable, Identifiable {
    case ollama = "ollama"
    case deepseek = "deepseek"
    case qwen = "qwen"
    case kimi = "kimi"
    case openaiCompatible = "openai_compatible"
    
    var id: String { rawValue }
    
    var displayName: String {
        switch self {
        case .ollama: return "Ollama (本地)"
        case .deepseek: return "DeepSeek"
        case .qwen: return "通义千问"
        case .kimi: return "Kimi"
        case .openaiCompatible: return "OpenAI 兼容"
        }
    }
    
    var defaultBaseUrl: String {
        switch self {
        case .ollama: return "http://localhost:11434/v1"
        case .deepseek: return "https://api.deepseek.com/v1"
        case .qwen: return "https://dashscope.aliyuncs.com/compatible-mode/v1"
        case .kimi: return "https://api.moonshot.cn/v1"
        case .openaiCompatible: return ""
        }
    }
    
    var defaultModel: String {
        switch self {
        case .ollama: return "qwen2.5:7b"
        case .deepseek: return "deepseek-chat"
        case .qwen: return "qwen-plus"
        case .kimi: return "moonshot-v1-8k"
        case .openaiCompatible: return ""
        }
    }
}

/// STT 后端
enum STTBackend: String, Codable, CaseIterable, Identifiable {
    case whisper = "whisper"
    case funasr = "funasr"
    
    var id: String { rawValue }
    
    var displayName: String {
        switch self {
        case .whisper: return "Whisper"
        case .funasr: return "FunASR"
        }
    }
}

/// TTS 后端
enum TTSBackend: String, Codable, CaseIterable, Identifiable {
    case chatt = "chatt"
    case edge = "edge"
    case fish = "fish"
    case cosyvoice = "cosyvoice"
    
    var id: String { rawValue }
    
    var displayName: String {
        switch self {
        case .chatt: return "ChatTTS"
        case .edge: return "Edge TTS"
        case .fish: return "Fish Speech"
        case .cosyvoice: return "CosyVoice"
        }
    }
}

/// 应用设置
struct AppSettings: Codable {
    // 服务器设置
    var serverHost: String = ""
    var serverPort: String = "8000"
    var useHTTPS: Bool = false
    
    // LLM 设置
    var llmProvider: LLMProvider = .ollama
    var llmModel: String = "qwen2.5:7b"
    var llmApiKey: String = ""
    var llmBaseUrl: String = "http://localhost:11434/v1"
    
    // Ollama 设置
    var ollamaBaseUrl: String = "http://localhost:11434/v1"
    
    // 语音设置
    var sttBackend: STTBackend = .whisper
    var ttsBackend: TTSBackend = .chatt
    
    // 本地存储键
    private static let storageKey = "CallioAppSettings"
    
    /// 保存设置到 UserDefaults
    func save() {
        if let data = try? JSONEncoder().encode(self) {
            UserDefaults.standard.set(data, forKey: Self.storageKey)
        }
    }
    
    /// 从 UserDefaults 加载设置
    static func load() -> AppSettings? {
        guard let data = UserDefaults.standard.data(forKey: storageKey),
              let settings = try? JSONDecoder().decode(AppSettings.self, from: data) else {
            return nil
        }
        return settings
    }
    
    /// 清除设置
    static func clear() {
        UserDefaults.standard.removeObject(forKey: storageKey)
    }
}

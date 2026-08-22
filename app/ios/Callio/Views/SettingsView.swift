//
//  SettingsView.swift
//  Callio
//
//  设置视图
//

import SwiftUI

/// 设置视图
struct SettingsView: View {
    @EnvironmentObject var appState: AppState
    @State private var isSaving = false
    @State private var saveStatusMessage = ""
    @State private var saveStatusIsSuccess = false
    
    var body: some View {
        ZStack {
            AppTheme.background.ignoresSafeArea()
            
            ScrollView {
                VStack(spacing: AppTheme.spacingXL) {
                    // 服务器设置
                    settingsSection(title: "服务器设置", icon: "server.rack") {
                        // 服务器地址
                        settingField(title: "服务器地址", placeholder: "例如 192.168.1.100") {
                            TextField("服务器地址", text: $appState.settings.serverHost)
                                .textFieldStyle(.plain)
                                .foregroundColor(AppTheme.text)
                                .keyboardType(.URL)
                                .autocapitalization(.none)
                        }
                        
                        // 端口
                        settingField(title: "端口", placeholder: "8000") {
                            TextField("8000", text: $appState.settings.serverPort)
                                .textFieldStyle(.plain)
                                .foregroundColor(AppTheme.text)
                                .keyboardType(.numberPad)
                        }
                        
                        // HTTPS 开关
                        Toggle("使用 HTTPS / WSS", isOn: $appState.settings.useHTTPS)
                            .tint(AppTheme.primary)
                            .padding()
                            .background(AppTheme.panelSoft)
                            .cornerRadius(AppTheme.cornerRadiusMedium)
                            .overlay(
                                RoundedRectangle(cornerRadius: AppTheme.cornerRadiusMedium)
                                    .stroke(AppTheme.panelBorder, lineWidth: 1)
                            )
                    }
                    
                    // LLM 设置
                    settingsSection(title: "LLM 设置", icon: "brain") {
                        // 提供商
                        settingField(title: "LLM 提供商") {
                            Picker("LLM 提供商", selection: $appState.settings.llmProvider) {
                                ForEach(LLMProvider.allCases) { provider in
                                    Text(provider.displayName).tag(provider)
                                }
                            }
                            .pickerStyle(.menu)
                            .tint(AppTheme.primary)
                            .onChange(of: appState.settings.llmProvider) { newValue in
                                applyProviderPreset(newValue)
                            }
                        }
                        
                        // 模型名称
                        settingField(title: "模型名称", placeholder: "qwen2.5:7b") {
                            TextField("模型名称", text: $appState.settings.llmModel)
                                .textFieldStyle(.plain)
                                .foregroundColor(AppTheme.text)
                                .autocapitalization(.none)
                        }
                        
                        // API Key
                        settingField(title: "API Key", placeholder: "本地 Ollama 可留空") {
                            SecureField("API Key", text: $appState.settings.llmApiKey)
                                .textFieldStyle(.plain)
                                .foregroundColor(AppTheme.text)
                                .autocapitalization(.none)
                        }
                        
                        // Base URL
                        settingField(title: "Base URL", placeholder: "http://localhost:11434/v1") {
                            TextField("Base URL", text: $appState.settings.llmBaseUrl)
                                .textFieldStyle(.plain)
                                .foregroundColor(AppTheme.text)
                                .keyboardType(.URL)
                                .autocapitalization(.none)
                        }
                    }
                    
                    // 语音设置
                    settingsSection(title: "语音设置", icon: "waveform") {
                        // STT 后端
                        settingField(title: "语音识别 (STT)") {
                            Picker("STT 后端", selection: $appState.settings.sttBackend) {
                                ForEach(STTBackend.allCases) { backend in
                                    Text(backend.displayName).tag(backend)
                                }
                            }
                            .pickerStyle(.menu)
                            .tint(AppTheme.primary)
                        }
                        
                        // TTS 后端
                        settingField(title: "语音合成 (TTS)") {
                            Picker("TTS 后端", selection: $appState.settings.ttsBackend) {
                                ForEach(TTSBackend.allCases) { backend in
                                    Text(backend.displayName).tag(backend)
                                }
                            }
                            .pickerStyle(.menu)
                            .tint(AppTheme.primary)
                        }
                    }
                    
                    // 保存按钮
                    VStack(spacing: AppTheme.spacingMedium) {
                        Button {
                            saveSettings()
                        } label: {
                            Text("保存设置")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(PrimaryButtonStyle(isLoading: isSaving))
                        
                        if !saveStatusMessage.isEmpty {
                            Text(saveStatusMessage)
                                .font(.system(size: 13))
                                .foregroundColor(saveStatusIsSuccess ? AppTheme.success : AppTheme.warning)
                                .multilineTextAlignment(.center)
                        }
                    }
                    
                    // 关于
                    VStack(spacing: 6) {
                        Text("Callio iOS")
                            .font(.system(size: 14, weight: .medium))
                            .foregroundColor(AppTheme.text)
                        
                        Text("全双工语音协作客户端")
                            .font(.system(size: 12))
                            .foregroundColor(AppTheme.muted)
                        
                        Text("Version 1.0.0")
                            .font(.system(size: 11))
                            .foregroundColor(AppTheme.muted.opacity(0.7))
                    }
                    .padding(.top, AppTheme.spacingLarge)
                    .padding(.bottom, AppTheme.spacingXXL)
                }
                .padding(.horizontal, AppTheme.spacingLarge)
                .padding(.top, AppTheme.spacingLarge)
            }
        }
        .navigationBarHidden(true)
    }
    
    // MARK: - 设置区块
    
    private func settingsSection<Content: View>(title: String, icon: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.spacingMedium) {
            HStack(spacing: AppTheme.spacingSmall) {
                Image(systemName: icon)
                    .font(.system(size: 14))
                    .foregroundColor(AppTheme.primary)
                
                Text(title)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(AppTheme.muted)
                    .textCase(.uppercase)
                    .tracking(0.8)
            }
            .padding(.bottom, 4)
            
            content()
        }
    }
    
    // MARK: - 设置字段
    
    private func settingField<Content: View>(title: String, placeholder: String? = nil, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.system(size: 13, weight: .medium))
                .foregroundColor(AppTheme.muted)
            
            content()
                .padding()
                .background(AppTheme.panelSoft)
                .cornerRadius(AppTheme.cornerRadiusMedium)
                .overlay(
                    RoundedRectangle(cornerRadius: AppTheme.cornerRadiusMedium)
                        .stroke(AppTheme.panelBorder, lineWidth: 1)
                )
        }
    }
    
    // MARK: - 操作
    
    private func applyProviderPreset(_ provider: LLMProvider) {
        // 应用预设的 Base URL
        if appState.settings.llmBaseUrl.isEmpty || isPresetBaseUrl(appState.settings.llmBaseUrl) {
            appState.settings.llmBaseUrl = provider.defaultBaseUrl
        }
        
        // 应用预设的模型
        if appState.settings.llmModel.isEmpty || isPresetModel(appState.settings.llmModel) {
            appState.settings.llmModel = provider.defaultModel
        }
    }
    
    private func isPresetBaseUrl(_ url: String) -> Bool {
        LLMProvider.allCases.contains { $0.defaultBaseUrl == url }
    }
    
    private func isPresetModel(_ model: String) -> Bool {
        LLMProvider.allCases.contains { $0.defaultModel == model }
    }
    
    private func saveSettings() {
        isSaving = true
        saveStatusMessage = ""
        
        // 保存到本地
        appState.saveSettings()
        
        // 同时保存服务器地址到 UserDefaults（供 APIService 使用）
        UserDefaults.standard.set(appState.settings.serverHost, forKey: "serverHost")
        UserDefaults.standard.set(appState.settings.serverPort, forKey: "serverPort")
        UserDefaults.standard.set(appState.settings.useHTTPS, forKey: "useHTTPS")
        
        // 尝试同步到服务器
        Task {
            do {
                let settingsDict: [String: String] = [
                    "CALLIO_LLM_PROVIDER": appState.settings.llmProvider.rawValue,
                    "CALLIO_LLM_MODEL": appState.settings.llmModel,
                    "CALLIO_LLM_API_KEY": appState.settings.llmApiKey,
                    "CALLIO_LLM_BASE_URL": appState.settings.llmBaseUrl,
                    "CALLIO_OLLAMA_BASE_URL": appState.settings.ollamaBaseUrl,
                    "CALLIO_STT_BACKEND": appState.settings.sttBackend.rawValue,
                    "CALLIO_TTS_BACKEND": appState.settings.ttsBackend.rawValue,
                    "CALLIO_HOST": appState.settings.serverHost,
                    "CALLIO_PORT": appState.settings.serverPort
                ]
                
                let configured = try await appState.apiService.saveSettings(settingsDict)
                
                DispatchQueue.main.async {
                    isSaving = false
                    saveStatusIsSuccess = configured
                    saveStatusMessage = configured
                        ? "设置已保存并同步到服务器"
                        : "设置已本地保存，但服务器端配置不完整"
                }
            } catch {
                DispatchQueue.main.async {
                    isSaving = false
                    saveStatusIsSuccess = false
                    saveStatusMessage = "设置已本地保存（服务器同步失败：\(error.localizedDescription)）"
                }
            }
        }
    }
}

struct SettingsView_Previews: PreviewProvider {
    static var previews: some View {
        NavigationStack {
            SettingsView()
        }
        .environmentObject(AppState())
        .preferredColorScheme(.dark)
    }
}

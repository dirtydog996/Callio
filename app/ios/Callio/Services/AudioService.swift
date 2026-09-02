//
//  AudioService.swift
//  Callio
//
//  音频服务 - 录音和播放
//

import Foundation
import AVFoundation

/// 音频服务
final class AudioService: NSObject {
    // MARK: - 属性
    private var audioEngine: AVAudioEngine?
    private var inputNode: AVAudioInputNode?
    private var isRecording = false
    
    // 播放相关
    private var playerNode: AVAudioPlayerNode?
    private var audioFormat: AVAudioFormat?
    private var playbackScheduled = false
    
    // 目标采样率
    static let targetSampleRate: Double = 16000
    private var inputFormatSampleRate: Double = 48000 // 默认值，实际从硬件动态获取
    
    // 录音回调
    var onAudioData: ((Data) -> Void)?
    
    // MARK: - 初始化
    
    override init() {
        super.init()
        setupAudioSession()
    }
    
    // MARK: - 音频会话配置
    
    private func setupAudioSession() {
        let session = AVAudioSession.sharedInstance()
        do {
            try session.setCategory(.playAndRecord, mode: .voiceChat, options: [.allowBluetooth, .defaultToSpeaker])
            try session.setActive(true, options: .notifyOthersOnDeactivation)
        } catch {
            print("配置音频会话失败: \(error.localizedDescription)")
        }
    }
    
    // MARK: - 麦克风权限
    
    /// 请求录音权限
    func requestRecordingPermission(completion: @escaping (Bool) -> Void) {
        let status = AVAudioSession.sharedInstance().recordPermission
        
        switch status {
        case .granted:
            completion(true)
        case .denied:
            completion(false)
        case .undetermined:
            AVAudioSession.sharedInstance().requestRecordPermission { granted in
                DispatchQueue.main.async {
                    completion(granted)
                }
            }
        @unknown default:
            completion(false)
        }
    }
    
    // MARK: - 录音控制
    
    /// 开始录音
    func startRecording(onPCMData: @escaping (Data) -> Void) {
        guard !isRecording else { return }
        
        onAudioData = onPCMData
        
        // 重新激活音频会话
        do {
            try AVAudioSession.sharedInstance().setActive(true, options: .notifyOthersOnDeactivation)
        } catch {
            print("激活音频会话失败: \(error.localizedDescription)")
        }
        
        // 创建音频引擎
        let engine = AVAudioEngine()
        audioEngine = engine
        
        let input = engine.inputNode
        inputNode = input
        
        // 获取输入格式（硬件格式）
        let hardwareFormat = input.outputFormat(forBus: 0)
        // 动态获取设备实际采样率
        inputFormatSampleRate = hardwareFormat.sampleRate
        
        // 设置录音格式为 16kHz 单声道
        guard let format = AVAudioFormat(
            commonFormat: .pcmFormatInt16,
            sampleRate: Self.targetSampleRate,
            channels: 1,
            interleaved: true
        ) else {
            print("无法创建目标音频格式")
            return
        }
        
        audioFormat = format
        
        // 安装录音回调
        let bufferSize: AVAudioFrameCount = 4096
        input.installTap(onBus: 0, bufferSize: bufferSize, format: hardwareFormat) { [weak self] buffer, time in
            guard let self = self, self.isRecording else { return }
            self.processAudioBuffer(buffer, from: hardwareFormat, to: format)
        }
        
        // 启动引擎
        do {
            // 先创建 playerNode 用于播放
            let player = AVAudioPlayerNode()
            playerNode = player
            engine.attach(player)
            
            if let outputFormat = audioFormat {
                engine.connect(player, to: engine.outputNode, format: outputFormat)
            }
            
            try engine.start()
            player.play()
            
            isRecording = true
        } catch {
            print("启动音频引擎失败: \(error.localizedDescription)")
        }
    }
    
    /// 停止录音
    func stopRecording() {
        guard isRecording else { return }
        
        isRecording = false
        
        inputNode?.removeTap(onBus: 0)
        audioEngine?.stop()
        audioEngine = nil
        inputNode = nil
        
        onAudioData = nil
    }
    
    // MARK: - 音频处理
    
    /// 处理音频缓冲区：重采样到 16kHz 并转为 Int16 PCM
    private func processAudioBuffer(_ buffer: AVAudioPCMBuffer, from sourceFormat: AVAudioFormat, to targetFormat: AVAudioFormat) {
        // 使用 AVAudioConverter 进行重采样
        guard let converter = AVAudioConverter(from: sourceFormat, to: targetFormat) else {
            return
        }
        
        let inputSampleRate = sourceFormat.sampleRate
        let outputSampleRate = targetFormat.sampleRate
        let ratio = inputSampleRate / outputSampleRate
        let outputFrameCount = AVAudioFrameCount(Double(buffer.frameLength) / ratio)
        
        guard let outputBuffer = AVAudioPCMBuffer(pcmFormat: targetFormat, frameCapacity: outputFrameCount) else {
            return
        }
        
        var error: NSError?
        let inputBlock: AVAudioConverterInputBlock = { inNumPackets, outStatus in
            outStatus.pointee = .haveData
            return buffer
        }
        
        converter.convert(to: outputBuffer, error: &error, withInputFrom: inputBlock)
        
        if let error = error {
            print("音频转换错误: \(error.localizedDescription)")
            return
        }
        
        // 将 Float32 转为 Int16
        guard let floatChannelData = outputBuffer.floatChannelData,
              outputBuffer.frameLength > 0 else {
            return
        }
        
        let frameCount = Int(outputBuffer.frameLength)
        let channels = Int(targetFormat.channelCount)
        var int16Data = Data(capacity: frameCount * channels * 2)
        
        for frame in 0..<frameCount {
            for channel in 0..<channels {
                let sample = floatChannelData[channel][frame]
                var int16Sample = Int16(max(-1.0, min(1.0, sample)) * 32767.0)
                int16Data.append(Data(bytes: &int16Sample, count: 2))
            }
        }
        
        // 通过回调发送 PCM 数据
        DispatchQueue.main.async { [weak self] in
            self?.onAudioData?(int16Data)
        }
    }
    
    // MARK: - 播放控制
    
    /// 播放 PCM 音频数据（16kHz, Int16, 单声道）
    func playPCMData(_ data: Data) {
        guard let player = playerNode,
              let format = audioFormat,
              data.count >= 2 else {
            return
        }
        
        // 将 Int16 转为 Float32
        let int16Count = data.count / 2
        var floatSamples = [Float](repeating: 0, count: int16Count)
        
        data.withUnsafeBytes { (rawBuffer: UnsafeRawBufferPointer) in
            guard let int16Pointer = rawBuffer.bindMemory(to: Int16.self).baseAddress else { return }
            for i in 0..<int16Count {
                floatSamples[i] = Float(int16Pointer[i]) / 32768.0
            }
        }
        
        // 创建 AVAudioPCMBuffer
        let frameCount = AVAudioFrameCount(int16Count)
        guard let pcmBuffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: frameCount) else {
            return
        }
        
        pcmBuffer.frameLength = frameCount
        
        if let channelData = pcmBuffer.floatChannelData?[0] {
            for i in 0..<int16Count {
                channelData[i] = floatSamples[i]
            }
        }
        
        // 调度播放
        player.scheduleBuffer(pcmBuffer)
    }
    
    /// 停止播放
    func stopPlayback() {
        playerNode?.stop()
        playerNode = nil
        playbackScheduled = false
    }
    
    // MARK: - 音量检测
    
    /// 获取当前录音音量（0-1）
    func getRecordingVolume() -> Float {
        // 简化实现，实际可通过 installTap 实时计算音量
        return isRecording ? 0.5 : 0
    }
}

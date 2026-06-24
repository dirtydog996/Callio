(function () {
    const TARGET_SAMPLE_RATE = 16000;
    const mode = document.body.dataset.clientMode || "web";

    const state = {
        ws: null,
        statusWs: null,
        sessionId: null,
        selectedSessionId: null,
        audioContext: null,
        mediaStream: null,
        audioProcessor: null,
        isRecording: false,
        playbackNextTime: 0,
        taskNodes: new Map(),
    };

    const elements = {
        statusPill: document.getElementById("statusPill"),
        statusHint: document.getElementById("statusHint"),
        messages: document.getElementById("messages"),
        tasks: document.getElementById("tasks"),
        sessions: document.getElementById("sessionList"),
        startBtn: document.getElementById("startBtn"),
        stopBtn: document.getElementById("stopBtn"),
        refreshBtn: document.getElementById("refreshBtn"),
        confirmAllBtn: document.getElementById("confirmAllBtn"),
        taskTitle: document.getElementById("taskTitle"),
        taskInput: document.getElementById("taskInput"),
        dispatchTaskBtn: document.getElementById("dispatchTaskBtn"),
        resumeLabel: document.getElementById("resumeLabel"),
    };

    function setStatus(kind, text, hint) {
        elements.statusPill.className = `pill ${kind || ""}`.trim();
        elements.statusPill.textContent = text;
        elements.statusHint.textContent = hint || "";
    }

    function addMessage(role, text, label) {
        const div = document.createElement("div");
        div.className = `message ${role}`;
        const meta = document.createElement("small");
        meta.textContent = label || (role === "user" ? "你" : "Callio");
        const body = document.createElement("div");
        body.textContent = text;
        div.append(meta, body);
        elements.messages.appendChild(div);
        elements.messages.scrollTop = elements.messages.scrollHeight;
    }

    function resetMessages() {
        elements.messages.innerHTML = "";
    }

    function formatSessionLabel(session) {
        const title = session.title || (session.session_id || "").slice(0, 8);
        const ended = session.ended_at ? "已结束" : "进行中";
        return `${title} · ${ended}`;
    }

    async function requestJson(path, options) {
        const url = new URL(path, window.location.origin);
        if (url.origin !== window.location.origin || !url.pathname.startsWith("/api/v1/")) {
            throw new Error("Unsupported request target");
        }
        const response = await fetch(url.toString(), options);
        if (!response.ok) {
            throw new Error(`${response.status} ${response.statusText}`);
        }
        return response.json();
    }

    function renderSessions(items) {
        elements.sessions.innerHTML = "";
        if (!items.length) {
            const empty = document.createElement("p");
            empty.className = "empty-state";
            empty.textContent = "还没有历史会话，直接开始新对话即可。";
            elements.sessions.appendChild(empty);
            return;
        }

        items.forEach((session) => {
            const button = document.createElement("button");
            button.className = "session-item";
            if (state.selectedSessionId === session.session_id) {
                button.classList.add("active");
            }
            button.type = "button";
            const title = document.createElement("strong");
            title.textContent = session.title || session.session_id.slice(0, 8);
            const meta = document.createElement("div");
            meta.className = "helper-text";
            meta.textContent = formatSessionLabel(session);
            button.append(title, meta);
            button.onclick = async () => {
                state.selectedSessionId = session.session_id;
                renderSessions(items);
                await preloadResumeSession(session.session_id);
                await refreshSessionTasks(session.session_id);
            };
            elements.sessions.appendChild(button);
        });
    }

    async function loadSessionOptions() {
        try {
            const data = await requestJson("/api/v1/sessions");
            renderSessions(data.items || []);
        } catch (error) {
            console.warn("Failed to load sessions", error);
        }
    }

    function renderStoredTranscript(transcript) {
        if (!transcript) return;
        transcript.split("\n").forEach((line) => {
            const text = line.trim();
            if (!text) return;
            if (text.startsWith("user:")) {
                addMessage("user", text.slice(5).trim(), "历史记录");
            } else if (text.startsWith("assistant:")) {
                addMessage("assistant", text.slice(10).trim(), "历史记录");
            }
        });
    }

    async function preloadResumeSession(sessionId) {
        const data = await requestJson(`/api/v1/sessions/${encodeURIComponent(sessionId)}`);
        if (!data.found || !data.session) return;
        resetMessages();
        renderStoredTranscript(data.session.transcript || "");
        if (data.session.summary) {
            addMessage("assistant", `续聊摘要：${data.session.summary}`, "摘要");
        }
        elements.resumeLabel.textContent = `当前目标会话：${data.session.title || sessionId.slice(0, 8)}`;
    }

    function taskCardClass(status) {
        return `task-card ${(status || "").toLowerCase()}`;
    }

    function taskTitle(event) {
        return event.feature_name || event.title || event.node_id || "任务";
    }

    function currentSessionRef() {
        return state.sessionId || state.selectedSessionId || "";
    }

    function renderTask(event) {
        if (!event || !event.event) return;
        const interesting = [
            "TASK_PROPOSED", "TASK_CONFIRMED", "TASK_RUNNING",
            "TASK_PROGRESS", "TASK_COMPLETED", "SUMMARY_UPDATED"
        ];
        if (!interesting.includes(event.event)) return;

        const nodeId = event.node_id || `${event.event}-${Date.now()}`;
        let card = state.taskNodes.get(nodeId);
        if (!card) {
            card = document.createElement("div");
            state.taskNodes.set(nodeId, card);
            elements.tasks.prepend(card);
        }

        const status = (event.status || event.phase || event.event).toString();
        const progress = event.progress != null ? Number(event.progress) : null;
        card.className = taskCardClass(status);
        card.innerHTML = "";

        const header = document.createElement("div");
        const title = document.createElement("strong");
        title.textContent = taskTitle(event);
        const meta = document.createElement("div");
        meta.className = "helper-text";
        meta.textContent = `${event.event} · ${status}${progress != null ? ` · ${progress}%` : ""}`;
        header.append(title, meta);
        card.appendChild(header);

        if (progress != null) {
            const wrap = document.createElement("div");
            wrap.className = "task-progress";
            const bar = document.createElement("div");
            bar.className = "task-progress-bar";
            bar.style.width = `${Math.max(0, Math.min(100, progress))}%`;
            wrap.appendChild(bar);
            card.appendChild(wrap);
        }

        const actions = document.createElement("div");
        actions.className = "task-actions";

        if (event.event === "TASK_PROPOSED" && currentSessionRef()) {
            const confirmBtn = document.createElement("button");
            confirmBtn.type = "button";
            confirmBtn.className = "primary-btn";
            confirmBtn.textContent = "确认";
            confirmBtn.onclick = () => postTaskAction("confirm", [nodeId]);
            const cancelBtn = document.createElement("button");
            cancelBtn.type = "button";
            cancelBtn.className = "ghost-btn";
            cancelBtn.textContent = "取消";
            cancelBtn.onclick = () => postTaskAction("cancel", [nodeId]);
            actions.append(confirmBtn, cancelBtn);
        }

        if (status === "RUNNING") {
            const stopBtn = document.createElement("button");
            stopBtn.type = "button";
            stopBtn.className = "danger-btn";
            stopBtn.textContent = "停止";
            stopBtn.onclick = () => cancelRunningTask(nodeId);
            actions.appendChild(stopBtn);
        }

        if (actions.children.length) {
            card.appendChild(actions);
        }
    }

    async function refreshSessionTasks(targetSessionId) {
        const sessionRef = targetSessionId || currentSessionRef();
        if (!sessionRef) {
            elements.tasks.innerHTML = "<p class='empty-state'>开始对话后，这里会展示后台任务与状态流。</p>";
            state.taskNodes.clear();
            return;
        }
        const data = await requestJson(`/api/v1/sessions/${encodeURIComponent(sessionRef)}/tasks`);
        elements.tasks.innerHTML = "";
        state.taskNodes.clear();
        const rows = [...(data.tasks || [])].reverse();
        if (!rows.length) {
            elements.tasks.innerHTML = "<p class='empty-state'>当前会话还没有后台任务。</p>";
        }
        rows.forEach((task) => {
            renderTask({
                event: task.phase === "PROPOSED" ? "TASK_PROPOSED" : "TASK_COMPLETED",
                node_id: task.node_id,
                feature_name: task.feature_name,
                status: task.status,
                phase: task.phase,
            });
        });
        (data.events || []).reverse().forEach(renderTask);
    }

    async function postTaskAction(action, nodeIds, confirmAll) {
        const sessionRef = currentSessionRef();
        if (!sessionRef) return;
        const path = action === "confirm"
            ? `/api/v1/sessions/${encodeURIComponent(sessionRef)}/tasks/confirm`
            : `/api/v1/sessions/${encodeURIComponent(sessionRef)}/tasks/cancel`;
        const body = action === "confirm"
            ? { node_ids: nodeIds, confirm_all: Boolean(confirmAll) }
            : { node_ids: nodeIds };
        const data = await requestJson(path, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
        addMessage("assistant", data.message || `任务已${action}`, "操作反馈");
        await refreshSessionTasks(sessionRef);
    }

    async function cancelRunningTask(nodeId) {
        const data = await requestJson(`/api/v1/tasks/${encodeURIComponent(nodeId)}/cancel`, { method: "POST" });
        addMessage("assistant", data.message || "已请求停止任务", "操作反馈");
        await refreshSessionTasks();
    }

    function connectStatusSocket() {
        const url = `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}/ws/status`;
        state.statusWs = new WebSocket(url);
        state.statusWs.onmessage = async (event) => {
            try {
                const data = JSON.parse(event.data);
                const sessionRef = currentSessionRef();
                if (sessionRef && data.session_id && data.session_id !== sessionRef) return;
                renderTask(data);
            } catch (error) {
                console.warn("status parse error", error);
            }
        };
    }

    function disconnectStatusSocket() {
        if (state.statusWs) {
            state.statusWs.close();
            state.statusWs = null;
        }
    }

    function stopDownlinkPlayback() {
        state.playbackNextTime = 0;
    }

    function playDownlinkPCM(arrayBuffer) {
        if (!state.audioContext || !arrayBuffer || arrayBuffer.byteLength < 2) return;
        const int16 = new Int16Array(arrayBuffer);
        const float32 = new Float32Array(int16.length);
        for (let i = 0; i < int16.length; i++) {
            float32[i] = int16[i] / 32768;
        }
        const buffer = state.audioContext.createBuffer(1, float32.length, TARGET_SAMPLE_RATE);
        buffer.getChannelData(0).set(float32);
        const source = state.audioContext.createBufferSource();
        source.buffer = buffer;
        source.connect(state.audioContext.destination);
        const now = state.audioContext.currentTime;
        const startAt = Math.max(now + 0.02, state.playbackNextTime);
        source.start(startAt);
        state.playbackNextTime = startAt + buffer.duration;
    }

    function floatTo16kPCM(input, inputSampleRate) {
        let samples = input;
        if (inputSampleRate !== TARGET_SAMPLE_RATE) {
            const ratio = inputSampleRate / TARGET_SAMPLE_RATE;
            const outLen = Math.floor(input.length / ratio);
            const resampled = new Float32Array(outLen);
            for (let i = 0; i < outLen; i++) {
                const pos = i * ratio;
                const idx = Math.floor(pos);
                const frac = pos - idx;
                const a = input[idx] || 0;
                const b = input[idx + 1] || a;
                resampled[i] = a + (b - a) * frac;
            }
            samples = resampled;
        }
        const int16 = new Int16Array(samples.length);
        for (let i = 0; i < samples.length; i++) {
            int16[i] = Math.max(-32768, Math.min(32767, samples[i] * 32767));
        }
        return int16.buffer;
    }

    function microphoneErrorMessage(error) {
        const name = error && error.name ? error.name : "";
        if (name === "NotAllowedError" || name === "PermissionDeniedError") {
            return "麦克风权限被拒绝，请在浏览器设置中允许访问后重试。";
        }
        if (name === "NotFoundError" || name === "DevicesNotFoundError") {
            return "未检测到可用麦克风，请检查设备设置。";
        }
        if (name === "SecurityError" || name === "NotSupportedError") {
            return "当前访问方式不支持麦克风；手机请改用 HTTPS。";
        }
        return error && error.message ? error.message : "无法启动麦克风";
    }

    function ensureMicrophoneSupported() {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            throw new Error("当前浏览器不支持麦克风访问。");
        }
        const host = window.location.hostname;
        const isLocalhost = host === "localhost" || host === "127.0.0.1";
        if (!window.isSecureContext && !isLocalhost) {
            throw new Error("当前为 HTTP 非安全连接，手机无法使用麦克风。请改用 HTTPS。");
        }
    }

    async function requestMicrophone() {
        ensureMicrophoneSupported();
        setStatus("warning", "等待权限", "请允许浏览器使用麦克风。");
        state.mediaStream = await navigator.mediaDevices.getUserMedia({
            audio: {
                channelCount: 1,
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
            }
        });
    }

    function startAudioPipeline() {
        if (!state.audioContext) {
            state.audioContext = new AudioContext();
        }
        const source = state.audioContext.createMediaStreamSource(state.mediaStream);
        state.audioProcessor = state.audioContext.createScriptProcessor(4096, 1, 1);
        const silentGain = state.audioContext.createGain();
        silentGain.gain.value = 0;
        source.connect(state.audioProcessor);
        state.audioProcessor.connect(silentGain);
        silentGain.connect(state.audioContext.destination);
        const captureRate = state.audioContext.sampleRate;
        state.audioProcessor.onaudioprocess = (e) => {
            if (!state.isRecording || !state.ws || state.ws.readyState !== WebSocket.OPEN) return;
            const inputData = e.inputBuffer.getChannelData(0);
            state.ws.send(floatTo16kPCM(inputData, captureRate));
        };
    }

    async function resumeAudioContext() {
        if (state.audioContext && state.audioContext.state === "suspended") {
            await state.audioContext.resume();
        }
    }

    function connectWebSocket() {
        const resumeId = state.selectedSessionId;
        let url = `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}/ws`;
        if (resumeId) {
            url += `?resume_session_id=${encodeURIComponent(resumeId)}`;
        }
        state.ws = new WebSocket(url);
        state.ws.binaryType = "arraybuffer";
        let connected = false;

        state.ws.onmessage = async (event) => {
            if (event.data instanceof ArrayBuffer) {
                playDownlinkPCM(event.data);
                return;
            }
            if (typeof event.data !== "string") return;
            const data = JSON.parse(event.data);
            if (data.type === "session") {
                state.sessionId = data.session_id;
                if (data.resumed) {
                    setStatus("success", "续聊中", data.title || state.sessionId.slice(0, 8));
                } else {
                    setStatus("success", "语音已连接", "可以直接开始说话。");
                }
                await refreshSessionTasks(state.sessionId);
            } else if (data.type === "transcription") {
                stopDownlinkPlayback();
                addMessage("user", data.text);
            } else if (data.type === "assistant") {
                addMessage("assistant", data.text);
            } else if (data.type === "interrupt") {
                stopDownlinkPlayback();
            }
        };

        state.ws.onerror = (error) => {
            console.error("WebSocket error", error);
            if (connected) {
                setStatus("danger", "连接错误", "语音通道已断开。");
                stopSession();
            }
        };

        state.ws.onclose = () => {
            if (state.isRecording) {
                setStatus("danger", "已断开", "语音会话已关闭。");
                stopSession();
            }
        };

        return new Promise((resolve, reject) => {
            state.ws.addEventListener("error", () => {
                if (!connected) reject(new Error("WebSocket 连接失败"));
            }, { once: true });
            state.ws.onopen = () => {
                connected = true;
                resolve();
            };
        });
    }

    function cleanupAudio() {
        if (state.audioProcessor) {
            state.audioProcessor.disconnect();
            state.audioProcessor.onaudioprocess = null;
            state.audioProcessor = null;
        }
        if (state.mediaStream) {
            state.mediaStream.getTracks().forEach((track) => track.stop());
            state.mediaStream = null;
        }
        if (state.audioContext) {
            state.audioContext.close();
            state.audioContext = null;
        }
    }

    async function startSession() {
        elements.startBtn.disabled = true;
        try {
            await requestMicrophone();
            if (state.selectedSessionId) {
                await preloadResumeSession(state.selectedSessionId);
            }
            connectStatusSocket();
            await connectWebSocket();
            startAudioPipeline();
            await resumeAudioContext();
            stopDownlinkPlayback();
            state.isRecording = true;
            elements.stopBtn.disabled = false;
            setStatus("success", "已连接", "全双工语音已启动。");
        } catch (error) {
            console.error(error);
            alert(`启动失败：${microphoneErrorMessage(error)}`);
            setStatus("danger", "启动失败", microphoneErrorMessage(error));
            stopSession();
        }
    }

    function stopSession() {
        state.isRecording = false;
        disconnectStatusSocket();
        stopDownlinkPlayback();
        cleanupAudio();
        if (state.ws) {
            state.ws.close();
            state.ws = null;
        }
        elements.startBtn.disabled = false;
        elements.stopBtn.disabled = true;
        state.sessionId = null;
        loadSessionOptions();
    }

    function summarizeTitle(text) {
        const clean = text.trim();
        if (!clean) return "手动任务";
        return clean.length > 24 ? `${clean.slice(0, 24)}…` : clean;
    }

    async function dispatchManualTask() {
        const description = elements.taskInput.value.trim();
        if (!description) return;
        const featureName = elements.taskTitle.value.trim() || summarizeTitle(description);
        const payload = {
            feature_name: featureName,
            description,
            difficulty_level: 1,
            session_id: currentSessionRef() || null,
        };
        const data = await requestJson("/api/v1/tasks/dispatch", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        addMessage("assistant", `已派发任务：${featureName}（${data.node_id}）`, "任务中心");
        elements.taskInput.value = "";
        elements.taskTitle.value = "";
        await refreshSessionTasks();
    }

    function bindQuickActions() {
        document.querySelectorAll("[data-task-prompt]").forEach((button) => {
            button.addEventListener("click", () => {
                const prompt = button.dataset.taskPrompt || "";
                if (!elements.taskInput.value.trim()) {
                    elements.taskInput.value = prompt;
                } else {
                    elements.taskInput.value = `${elements.taskInput.value.trim()}\n${prompt}`;
                }
                elements.taskInput.focus();
            });
        });
    }

    elements.startBtn.addEventListener("click", startSession);
    elements.stopBtn.addEventListener("click", stopSession);
    elements.refreshBtn.addEventListener("click", async () => {
        await loadSessionOptions();
        await refreshSessionTasks();
    });
    elements.confirmAllBtn.addEventListener("click", async () => {
        await postTaskAction("confirm", [], true);
    });
    elements.dispatchTaskBtn.addEventListener("click", async () => {
        try {
            await dispatchManualTask();
        } catch (error) {
            alert(`任务派发失败：${error.message}`);
        }
    });

    bindQuickActions();
    loadSessionOptions();
    refreshSessionTasks();

    if (mode === "mobile") {
        setStatus("warning", "移动端就绪", "推荐使用 HTTPS 访问以启用麦克风。");
    } else {
        setStatus("warning", "待连接", "选择历史会话或开始新一轮语音协作。");
    }
})();

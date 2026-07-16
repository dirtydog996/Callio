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
        assistantDraft: {
            messageBody: null,
            reportItem: null,
            label: "",
            at: 0,
        },
    };

    const elements = {
        statusPill: document.getElementById("statusPill"),
        statusHint: document.getElementById("statusHint"),
        messages: document.getElementById("messages"),
        tasks: document.getElementById("tasks"),
        liveReport: document.getElementById("liveReport"),
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

    // ---- Toast notification system ----
    const _toastContainer = (() => {
        const el = document.createElement("div");
        el.className = "toast-container";
        document.body.appendChild(el);
        return el;
    })();

    function showToast(message, kind, duration) {
        const toast = document.createElement("div");
        toast.className = `toast ${kind || ""}`.trim();
        toast.textContent = message;
        _toastContainer.appendChild(toast);
        setTimeout(() => {
            toast.style.opacity = "0";
            toast.style.transform = "translateX(120%)";
            setTimeout(() => toast.remove(), 320);
        }, duration == null ? 3500 : duration);
    }

    // ---- Session report modal ----
    const _STATUS_INFO = {
        COMPLETED: { icon: "✓", label: "Completed", cls: "completed" },
        SUCCESS:   { icon: "✓", label: "Completed", cls: "completed" },
        PENDING:   { icon: "◎", label: "Pending confirmation", cls: "pending" },
        CONFIRMED: { icon: "◉", label: "Pending execution", cls: "pending" },
        RUNNING:   { icon: "⟳", label: "Running", cls: "running" },
        FAILED:    { icon: "✗", label: "Failed", cls: "failed" },
        CANCELLED: { icon: "⊘", label: "Cancelled", cls: "failed" },
    };

    function _statusInfo(status) {
        return _STATUS_INFO[(status || "").toUpperCase()] || { icon: "·", label: status || "Unknown", cls: "" };
    }

    async function showSessionReport(sessionId) {
        let sessionData, tasksData;
        try {
            [sessionData, tasksData] = await Promise.all([
                requestJson(`/api/v1/sessions/${encodeURIComponent(sessionId)}`),
                requestJson(`/api/v1/sessions/${encodeURIComponent(sessionId)}/tasks`),
            ]);
        } catch (e) {
            return;
        }
        if (!sessionData || !sessionData.found) return;
        const session = sessionData.session;
        const tasks = (tasksData && tasksData.tasks) ? tasksData.tasks : [];
        if (!session.summary && !tasks.length) return;

        const overlay = document.createElement("div");
        overlay.className = "modal-overlay";

        const modal = document.createElement("div");
        modal.className = "modal";
        modal.setAttribute("role", "dialog");
        modal.setAttribute("aria-modal", "true");

        // Header
        const header = document.createElement("div");
        header.className = "modal-header";
        const titleEl = document.createElement("h2");
        titleEl.className = "modal-title";
        titleEl.textContent = `📋 ${session.title || "Call Summary"}`;
        const closeBtn = document.createElement("button");
        closeBtn.type = "button";
        closeBtn.className = "ghost-btn";
        closeBtn.style.padding = "8px 16px";
        closeBtn.textContent = "Close";
        closeBtn.onclick = () => overlay.remove();
        header.append(titleEl, closeBtn);
        modal.appendChild(header);

        // Meta
        const metaEl = document.createElement("div");
        metaEl.className = "modal-meta";
        try {
            const ts = session.ended_at || session.created_at;
            metaEl.textContent = ts
                ? `Call time: ${new Date(ts).toLocaleString("en-US")}`
                : "Call ended";
        } catch (_) {
            metaEl.textContent = "Call ended";
        }
        modal.appendChild(metaEl);

        // Summary
        if (session.summary) {
            const sumLabel = document.createElement("div");
            sumLabel.className = "modal-section-label";
            sumLabel.textContent = "Session Summary";
            const sumText = document.createElement("div");
            sumText.className = "modal-summary-text";
            sumText.textContent = session.summary;
            modal.append(sumLabel, sumText);
        }

        // Tasks / todos
        if (tasks.length) {
            const todoLabel = document.createElement("div");
            todoLabel.className = "modal-section-label";
            todoLabel.textContent = `Tasks (${tasks.length})`;
            modal.appendChild(todoLabel);
            tasks.forEach((task) => {
                const si = _statusInfo(task.status);
                const item = document.createElement("div");
                item.className = "todo-item";

                const iconEl = document.createElement("div");
                iconEl.className = `todo-icon ${si.cls}`;
                iconEl.textContent = si.icon;

                const content = document.createElement("div");
                content.className = "todo-content";
                const name = document.createElement("div");
                name.className = "todo-name";
                name.textContent = task.feature_name || task.node_id;
                content.appendChild(name);
                if (task.description) {
                    const desc = document.createElement("div");
                    desc.className = "todo-desc";
                    desc.textContent = task.description;
                    content.appendChild(desc);
                }

                const badge = document.createElement("div");
                badge.className = `todo-badge ${si.cls}`;
                badge.textContent = si.label;

                item.append(iconEl, content, badge);
                modal.appendChild(item);
            });
        }

        // Footer
        const footer = document.createElement("div");
        footer.className = "modal-footer";
        const doneBtn = document.createElement("button");
        doneBtn.type = "button";
        doneBtn.className = "primary-btn";
        doneBtn.textContent = "Done";
        doneBtn.onclick = () => overlay.remove();
        footer.appendChild(doneBtn);
        modal.appendChild(footer);

        overlay.appendChild(modal);
        document.body.appendChild(overlay);
        overlay.addEventListener("click", (e) => {
            if (e.target === overlay) overlay.remove();
        });
        closeBtn.focus();
    }

    function setStatus(kind, text, hint) {
        elements.statusPill.className = `pill ${kind || ""}`.trim();
        elements.statusPill.textContent = text;
        elements.statusHint.textContent = hint || "";
    }

    function normalizeDisplayText(value) {
        const text = value == null ? "" : String(value);
        const unified = text.replace(/\r\n?/g, "\n");
        const lines = unified.split("\n");
        const nonEmpty = lines.filter((line) => line.length > 0);
        const charByCharLines = nonEmpty.length >= 8 && nonEmpty.every((line) => line.trim().length <= 1);
        if (charByCharLines) {
            return nonEmpty.join("");
        }
        return unified;
    }

    function resetAssistantDraft() {
        state.assistantDraft.messageBody = null;
        state.assistantDraft.reportItem = null;
        state.assistantDraft.label = "";
        state.assistantDraft.at = 0;
    }

    function mergeText(base, fragment) {
        if (!base) return fragment || "";
        if (!fragment) return base;
        return `${base}${fragment}`;
    }

    function addMessage(role, text, label, options) {
        const opts = options || {};
        const normalizedText = normalizeDisplayText(text);
        const stream = Boolean(opts.stream) && role === "assistant";
        const activeLabel = label || "Callio";
        const canAppend = stream
            && state.assistantDraft.messageBody
            && state.assistantDraft.label === activeLabel
            && Date.now() - state.assistantDraft.at < 2500;
        if (canAppend) {
            state.assistantDraft.messageBody.textContent = mergeText(state.assistantDraft.messageBody.textContent, normalizedText);
            state.assistantDraft.at = Date.now();
            addLiveReport(role, normalizedText, label, { stream: true });
            elements.messages.scrollTop = elements.messages.scrollHeight;
            return;
        }
        if (!stream) {
            resetAssistantDraft();
        }
        const div = document.createElement("div");
        div.className = `message ${role}`;
        const meta = document.createElement("small");
        const _msgTime = new Date().toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
        meta.textContent = `${label || (role === "user" ? "You" : "Callio")} · ${_msgTime}`;
        const body = document.createElement("div");
        body.textContent = normalizedText;
        div.append(meta, body);
        elements.messages.appendChild(div);
        elements.messages.scrollTop = elements.messages.scrollHeight;
        if (stream) {
            state.assistantDraft.messageBody = body;
            state.assistantDraft.label = activeLabel;
            state.assistantDraft.at = Date.now();
        }
        addLiveReport(role, normalizedText, label, { stream });
    }

    function resetMessages() {
        elements.messages.innerHTML = "";
        resetAssistantDraft();
    }

    function resetLiveReport() {
        if (!elements.liveReport) return;
        elements.liveReport.innerHTML = "<p class='empty-state'>User and assistant text appears here live after the conversation starts.</p>";
        state.assistantDraft.reportItem = null;
    }

    function addLiveReport(role, text, label, options) {
        if (!elements.liveReport || !text) return;
        const opts = options || {};
        if (Boolean(opts.stream) && role === "assistant" && state.assistantDraft.reportItem) {
            state.assistantDraft.reportItem.textContent = mergeText(state.assistantDraft.reportItem.textContent, text);
            return;
        }
        const empty = elements.liveReport.querySelector(".empty-state");
        if (empty) empty.remove();
        const item = document.createElement("div");
        item.className = `report-item ${role}`;
        const time = new Date().toLocaleTimeString();
        item.textContent = `[${time}] ${label || (role === "user" ? "You" : "Callio")}: ${text}`;
        elements.liveReport.prepend(item);
        if (Boolean(opts.stream) && role === "assistant") {
            state.assistantDraft.reportItem = item;
        }
    }

    function formatSessionLabel(session) {
        const title = session.title || (session.session_id || "").slice(0, 8);
        const ended = session.ended_at ? "Ended" : "Active";
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
            empty.textContent = "No previous sessions yet — start a new conversation.";
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
                addMessage("user", text.slice(5).trim(), "History");
            } else if (text.startsWith("assistant:")) {
                addMessage("assistant", text.slice(10).trim(), "History");
            }
        });
    }

    async function preloadResumeSession(sessionId) {
        const data = await requestJson(`/api/v1/sessions/${encodeURIComponent(sessionId)}`);
        if (!data.found || !data.session) return;
        resetMessages();
        resetLiveReport();
        renderStoredTranscript(data.session.transcript || "");
        if (data.session.summary) {
            addMessage("assistant", `Resumed summary: ${data.session.summary}`, "Summary");
        }
        elements.resumeLabel.textContent = `Current target session: ${data.session.title || sessionId.slice(0, 8)}`;
    }

    function taskCardClass(status) {
        return `task-card ${(status || "").toLowerCase()}`;
    }

    function taskTitle(event) {
        return event.feature_name || event.title || event.node_id || "Task";
    }

    function currentSessionRef() {
        return state.sessionId || state.selectedSessionId || "";
    }

    function _kindLabel(kind) {
        const map = { ANALYZE: "Analyze", EXECUTE: "Execute", SUMMARIZE: "Summarize" };
        return map[(kind || "").toUpperCase()] || kind || "";
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

        // Header row: title + kind badge
        const header = document.createElement("div");
        header.className = "task-card-header";
        const title = document.createElement("strong");
        title.textContent = taskTitle(event);
        header.appendChild(title);
        const kindLabel = _kindLabel(event.kind);
        if (kindLabel) {
            const badge = document.createElement("span");
            badge.className = `task-kind-badge ${(event.kind || "").toLowerCase()}`;
            badge.textContent = kindLabel;
            header.appendChild(badge);
        }
        const meta = document.createElement("div");
        meta.className = "helper-text";
        meta.textContent = `${event.event} · ${status}${progress != null ? ` · ${progress}%` : ""}`;
        header.appendChild(meta);
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

        // Show result preview for completed tasks
        const resultText = event.result_summary || event.report;
        if (resultText && (event.event === "TASK_COMPLETED" || status === "SUCCESS")) {
            const preview = document.createElement("div");
            preview.className = "task-result-preview";
            preview.textContent = resultText.length > 200
                ? resultText.slice(0, 200) + "…"
                : resultText;
            card.appendChild(preview);
        }

        // Show completion toast for successful tasks arriving via WebSocket
        if (event.event === "TASK_COMPLETED" && status === "SUCCESS" && event._live) {
            const toastMsg = resultText
                ? `✓ ${taskTitle(event)}: ${resultText.slice(0, 80)}${resultText.length > 80 ? "…" : ""}`
                : `✓ Task completed: ${taskTitle(event)}`;
            showToast(toastMsg, "success", 5000);
        }

        const actions = document.createElement("div");
        actions.className = "task-actions";

        if (event.event === "TASK_PROPOSED" && currentSessionRef()) {
            const confirmBtn = document.createElement("button");
            confirmBtn.type = "button";
            confirmBtn.className = "primary-btn";
            confirmBtn.textContent = "Confirm";
            confirmBtn.onclick = () => postTaskAction("confirm", [nodeId]);
            const cancelBtn = document.createElement("button");
            cancelBtn.type = "button";
            cancelBtn.className = "ghost-btn";
            cancelBtn.textContent = "Cancel";
            cancelBtn.onclick = () => postTaskAction("cancel", [nodeId]);
            actions.append(confirmBtn, cancelBtn);
        }

        if (status === "RUNNING") {
            const stopBtn = document.createElement("button");
            stopBtn.type = "button";
            stopBtn.className = "danger-btn";
            stopBtn.textContent = "Stop";
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
            elements.tasks.innerHTML = "<p class='empty-state'>Background tasks and status updates appear here after you start a conversation.</p>";
            state.taskNodes.clear();
            return;
        }
        const data = await requestJson(`/api/v1/sessions/${encodeURIComponent(sessionRef)}/tasks`);
        elements.tasks.innerHTML = "";
        state.taskNodes.clear();
        const rows = [...(data.tasks || [])].reverse();
        if (!rows.length) {
            elements.tasks.innerHTML = "<p class='empty-state'>No background tasks yet for this session.</p>";
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
        addMessage("assistant", data.message || `Task ${action}`, "Action Feedback");
        await refreshSessionTasks(sessionRef);
    }

    async function cancelRunningTask(nodeId) {
        const data = await requestJson(`/api/v1/tasks/${encodeURIComponent(nodeId)}/cancel`, { method: "POST" });
        addMessage("assistant", data.message || "Stop requested", "Action Feedback");
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
                // Mark as live so renderTask can trigger completion toasts.
                renderTask({ ...data, _live: true });
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
            return "Microphone permission was denied. Allow access in your browser settings and try again.";
        }
        if (name === "NotFoundError" || name === "DevicesNotFoundError") {
            return "No microphone was detected. Check your device settings.";
        }
        if (name === "SecurityError" || name === "NotSupportedError") {
            return "This access method does not support microphone use; on mobile, switch to HTTPS.";
        }
        return error && error.message ? error.message : "Could not start the microphone";
    }

    function getUserMediaFn() {
        if (navigator.mediaDevices && typeof navigator.mediaDevices.getUserMedia === "function") {
            return (constraints) => navigator.mediaDevices.getUserMedia(constraints);
        }
        const legacy = navigator.getUserMedia || navigator.webkitGetUserMedia || navigator.mozGetUserMedia || navigator.msGetUserMedia;
        if (typeof legacy === "function") {
            return (constraints) => new Promise((resolve, reject) => legacy.call(navigator, constraints, resolve, reject));
        }
        return null;
    }

    function ensureMicrophoneSupported() {
        const host = window.location.hostname;
        const isLocalhost = host === "localhost" || host === "127.0.0.1";
        if (!window.isSecureContext && !isLocalhost) {
            throw new Error("This is an insecure HTTP connection, so mobile cannot use the microphone. Switch to HTTPS.");
        }
        if (!getUserMediaFn()) {
            throw new Error("This browser does not support microphone access.");
        }
    }

    async function requestMicrophone() {
        ensureMicrophoneSupported();
        setStatus("warning", "Waiting for permission", "Please allow the browser to use the microphone.");
        const requestUserMedia = getUserMediaFn();
        state.mediaStream = await requestUserMedia({
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
                resetAssistantDraft();
                state.sessionId = data.session_id;
                if (data.resumed) {
                    setStatus("success", "Resuming session", data.title || state.sessionId.slice(0, 8));
                } else {
                    setStatus("success", "Voice connected", "You can start speaking now.");
                }
                await refreshSessionTasks(state.sessionId);
            } else if (data.type === "transcription") {
                resetAssistantDraft();
                stopDownlinkPlayback();
                addMessage("user", data.text);
            } else if (data.type === "assistant") {
                addMessage("assistant", data.text, undefined, { stream: true });
            } else if (data.type === "interrupt") {
                resetAssistantDraft();
                stopDownlinkPlayback();
            }
        };

        state.ws.onerror = (error) => {
            console.error("WebSocket error", error);
            if (connected) {
                setStatus("danger", "Connection error", "The voice channel was disconnected.");
                stopSession(true);
            }
        };

        state.ws.onclose = () => {
            if (state.isRecording) {
                setStatus("danger", "Disconnected", "The voice session has closed.");
                stopSession(true);
            }
        };

        return new Promise((resolve, reject) => {
            state.ws.addEventListener("error", () => {
                if (!connected) reject(new Error("WebSocket connection failed"));
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
            document.body.setAttribute("data-recording", "true");
            elements.stopBtn.disabled = false;
            setStatus("success", "Connected", "Full-duplex voice is running.");
        } catch (error) {
            console.error(error);
            showToast(`Start failed: ${microphoneErrorMessage(error)}`, "danger", 6000);
            setStatus("danger", "Start failed", microphoneErrorMessage(error));
            stopSession(true);
        }
    }

    function stopSession(skipStatusUpdate) {
        document.body.removeAttribute("data-recording");
        const endedSessionId = state.sessionId;
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
        if (!skipStatusUpdate) {
            setStatus("", "Disconnected", "Conversation ended.");
        }
        resetLiveReport();
        loadSessionOptions();
        if (endedSessionId) {
            setTimeout(() => showSessionReport(endedSessionId).catch(() => {}), 500);
        }
    }

    function summarizeTitle(text) {
        const clean = text.trim();
        if (!clean) return "Manual task";
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
        addMessage("assistant", `Dispatched task: ${featureName} (${data.node_id})`, "Task Center");
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
            showToast(`Task dispatch failed: ${error.message}`, "danger");
        }
    });

    bindQuickActions();
    loadSessionOptions();
    refreshSessionTasks();
    resetLiveReport();

    if (mode === "mobile") {
        setStatus("warning", "Mobile ready", "Use HTTPS to enable microphone access.");
    } else {
        setStatus("warning", "Disconnected", "Choose a previous session or start a new voice collaboration round.");
    }
})();

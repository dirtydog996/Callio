(function () {
    const TARGET_SAMPLE_RATE = 16000;
    const mode = document.body.dataset.clientMode || "web";
    const LAST_SESSION_STORAGE_KEY = "callio.lastSessionId";
    const SETTINGS_READY_STORAGE_KEY = "callio.settingsReady";

    function loadStoredSessionId() {
        try {
            return localStorage.getItem(LAST_SESSION_STORAGE_KEY) || null;
        } catch (_) {
            return null;
        }
    }

    function storeSessionId(sessionId) {
        try {
            if (sessionId) {
                localStorage.setItem(LAST_SESSION_STORAGE_KEY, sessionId);
            } else {
                localStorage.removeItem(LAST_SESSION_STORAGE_KEY);
            }
        } catch (_) {
            // Ignore storage failures (private mode / restricted envs).
        }
    }

    function loadStoredSettingsReady() {
        try {
            return localStorage.getItem(SETTINGS_READY_STORAGE_KEY) === "1";
        } catch (_) {
            return false;
        }
    }

    function storeSettingsReady(value) {
        try {
            localStorage.setItem(SETTINGS_READY_STORAGE_KEY, value ? "1" : "0");
        } catch (_) {
            // Ignore storage failures.
        }
    }

    const state = {
        ws: null,
        statusWs: null,
        sessionId: null,
        selectedSessionId: loadStoredSessionId(),
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
        settingsReady: loadStoredSettingsReady(),
        ollamaModels: [],
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
        settingsModal: document.getElementById("settingsModal"),
        openSettingsBtn: document.getElementById("openSettingsBtn"),
        openSettingsInlineBtn: document.getElementById("openSettingsInlineBtn"),
        closeSettingsBtn: document.getElementById("closeSettingsBtn"),
        saveSettingsBtn: document.getElementById("saveSettingsBtn"),
        setupGate: document.getElementById("setupGate"),
        settingLlmProvider: document.getElementById("settingLlmProvider"),
        settingLlmModel: document.getElementById("settingLlmModel"),
        settingLlmApiKey: document.getElementById("settingLlmApiKey"),
        settingLlmBaseUrl: document.getElementById("settingLlmBaseUrl"),
        settingOllamaBaseUrl: document.getElementById("settingOllamaBaseUrl"),
        settingSttBackend: document.getElementById("settingSttBackend"),
        settingTtsBackend: document.getElementById("settingTtsBackend"),
        settingHost: document.getElementById("settingHost"),
        settingPort: document.getElementById("settingPort"),
        settingOllamaModelSearch: document.getElementById("settingOllamaModelSearch"),
        ollamaModelOptions: document.getElementById("ollamaModelOptions"),
        refreshOllamaModelsBtn: document.getElementById("refreshOllamaModelsBtn"),
        ollamaModelGroup: document.getElementById("ollamaModelGroup"),
        ollamaStatus: document.getElementById("ollamaStatus"),
        providerHint: document.getElementById("providerHint"),
        saveSettingsStatus: document.getElementById("saveSettingsStatus"),
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

    function applySettingsReadyUI() {
        if (mode !== "web") {
            return;
        }
        document.body.setAttribute("data-settings-ready", state.settingsReady ? "true" : "false");
        if (elements.setupGate) {
            elements.setupGate.hidden = state.settingsReady;
        }
        if (!state.settingsReady) {
            setStatus("warning", "Settings required", "Complete setup wizard before starting voice conversation.");
        }
    }

    function openSettingsModal() {
        if (!elements.settingsModal) return;
        elements.settingsModal.classList.add("is-open");
        elements.settingsModal.removeAttribute("hidden");
        elements.settingsModal.hidden = false;
        setSaveSettingsStatus("Review settings and save when you are ready.", "info");
        loadOllamaModels().catch(() => {});
    }

    function closeSettingsModal() {
        if (!elements.settingsModal) return;
        elements.settingsModal.classList.remove("is-open");
        elements.settingsModal.setAttribute("hidden", "hidden");
        elements.settingsModal.hidden = true;
    }

    function applyProviderSpecificUI() {
        const provider = elements.settingLlmProvider?.value || "ollama";
        document.querySelectorAll("[data-provider-scope]").forEach((node) => {
            const scopes = (node.getAttribute("data-provider-scope") || "").split(/\s+/).filter(Boolean);
            const shouldShow = scopes.includes(provider) || (scopes.includes("remote-auth") && provider !== "ollama");
            node.hidden = !shouldShow;
        });
        if (!elements.ollamaModelGroup) return;
        const showOllama = provider === "ollama";
        elements.ollamaModelGroup.hidden = !showOllama;
        if (elements.providerHint) {
            elements.providerHint.className = "field-note info field-span-2";
            if (provider === "ollama") {
                elements.providerHint.textContent = "Ollama uses a local base URL and can auto-discover installed models from the running service.";
            } else if (provider === "openai_compatible") {
                elements.providerHint.textContent = "OpenAI-compatible providers usually require both a base URL and an API key.";
            } else {
                elements.providerHint.textContent = "Hosted providers usually require an API key and a provider-specific model name.";
            }
        }
        if (!showOllama && elements.ollamaStatus) {
            elements.ollamaStatus.className = "field-note";
            elements.ollamaStatus.textContent = "Ollama model discovery is only used when the provider is set to ollama.";
        }
    }

    function setSaveSettingsStatus(message, kind) {
        if (!elements.saveSettingsStatus) return;
        elements.saveSettingsStatus.className = `field-note modal-status ${kind || "info"}`.trim();
        elements.saveSettingsStatus.textContent = message;
    }

    function setOllamaStatus(message, kind) {
        if (!elements.ollamaStatus) return;
        elements.ollamaStatus.className = `field-note ${kind || ""}`.trim();
        elements.ollamaStatus.textContent = message;
    }

    async function loadOllamaModelsFromBrowser(baseUrl) {
        const normalized = (baseUrl || "http://localhost:11434/v1").trim().replace(/\/$/, "");
        const tagsUrl = normalized.endsWith("/v1")
            ? `${normalized.slice(0, -3)}/api/tags`
            : `${normalized}/api/tags`;
        const response = await fetch(tagsUrl, { method: "GET" });
        if (!response.ok) {
            throw new Error(`${response.status} ${response.statusText}`);
        }
        const payload = await response.json();
        const models = Array.isArray(payload?.models)
            ? payload.models
                .map((item) => item && item.name ? String(item.name).trim() : "")
                .filter(Boolean)
            : [];
        return Array.from(new Set(models)).sort();
    }

    function fillOllamaModelSelect(models, selectedModel) {
        if (!elements.ollamaModelOptions) return;
        const normalized = Array.isArray(models) ? models : [];
        elements.ollamaModelOptions.innerHTML = "";

        normalized.forEach((name) => {
            const option = document.createElement("option");
            option.value = name;
            elements.ollamaModelOptions.appendChild(option);
        });

        if (elements.settingOllamaModelSearch) {
            elements.settingOllamaModelSearch.placeholder = normalized.length
                ? "Search or type an installed model"
                : "No installed model found";
            elements.settingOllamaModelSearch.value = selectedModel || "";
        }
    }

    async function loadOllamaModels() {
        if (mode !== "web" || !elements.settingOllamaModelSearch) return;
        const provider = elements.settingLlmProvider?.value || "ollama";
        if (provider !== "ollama") {
            applyProviderSpecificUI();
            return;
        }

        const rawBaseUrl = elements.settingOllamaBaseUrl?.value.trim() || "";
        const baseUrl = encodeURIComponent(rawBaseUrl);
        elements.settingOllamaModelSearch.placeholder = "Loading installed models...";
        setOllamaStatus("Checking Ollama service and installed models...", "");
        try {
            const data = await requestJson(`/api/v1/settings/ollama-models?base_url=${baseUrl}`);
            state.ollamaModels = data.models || [];
            fillOllamaModelSelect(state.ollamaModels, elements.settingLlmModel?.value.trim() || "");
            if (data.reachable) {
                if (state.ollamaModels.length) {
                    setOllamaStatus(`Ollama is reachable at ${data.base_url}. Found ${state.ollamaModels.length} installed model${state.ollamaModels.length > 1 ? "s" : ""}.`, "success");
                } else {
                    setOllamaStatus(`Ollama is reachable at ${data.base_url}, but no installed models were returned. Run 'ollama list' or pull a model first.`, "warning");
                }
            } else {
                try {
                    const browserModels = await loadOllamaModelsFromBrowser(rawBaseUrl || "http://localhost:11434/v1");
                    state.ollamaModels = browserModels;
                    fillOllamaModelSelect(state.ollamaModels, elements.settingLlmModel?.value.trim() || "");
                    if (browserModels.length) {
                        setOllamaStatus(`Server-side detection could not reach Ollama, but your browser reached ${rawBaseUrl || "http://localhost:11434/v1"} and found ${browserModels.length} installed model${browserModels.length > 1 ? "s" : ""}. This usually means Ollama is running on your local machine while the app runs in a container or remote workspace.`, "success");
                        return;
                    }
                } catch (_) {
                    // Ignore browser fallback errors and show the server-side diagnostic below.
                }
                setOllamaStatus(`Ollama is not reachable at ${data.base_url}. ${data.hint ? `${data.hint} ` : ""}Error: ${data.error || "unknown error"}`, "danger");
                showToast(`Ollama is not reachable: ${data.error || "unknown error"}`, "warning", 5000);
            }
        } catch (error) {
            fillOllamaModelSelect([], "");
            setOllamaStatus(`Failed to load Ollama models. Check whether the service is running and whether the base URL is correct. Error: ${error.message}`, "danger");
            showToast(`Failed to load Ollama models: ${error.message}`, "warning", 5000);
        }
    }

    function collectSettingsPayload() {
        return {
            CALLIO_LLM_PROVIDER: elements.settingLlmProvider?.value || "",
            CALLIO_LLM_MODEL: elements.settingLlmModel?.value.trim() || "",
            CALLIO_LLM_API_KEY: elements.settingLlmApiKey?.value.trim() || "",
            CALLIO_LLM_BASE_URL: elements.settingLlmBaseUrl?.value.trim() || "",
            CALLIO_OLLAMA_BASE_URL: elements.settingOllamaBaseUrl?.value.trim() || "",
            CALLIO_STT_BACKEND: elements.settingSttBackend?.value || "",
            CALLIO_TTS_BACKEND: elements.settingTtsBackend?.value || "",
            CALLIO_HOST: elements.settingHost?.value.trim() || "",
            CALLIO_PORT: elements.settingPort?.value.trim() || "",
        };
    }

    function fillSettingsForm(data) {
        if (!data) return;
        if (elements.settingLlmProvider) elements.settingLlmProvider.value = data.CALLIO_LLM_PROVIDER || "ollama";
        if (elements.settingLlmModel) elements.settingLlmModel.value = data.CALLIO_LLM_MODEL || "";
        if (elements.settingLlmApiKey) elements.settingLlmApiKey.value = data.CALLIO_LLM_API_KEY || "";
        if (elements.settingLlmBaseUrl) elements.settingLlmBaseUrl.value = data.CALLIO_LLM_BASE_URL || "";
        if (elements.settingOllamaBaseUrl) elements.settingOllamaBaseUrl.value = data.CALLIO_OLLAMA_BASE_URL || "";
        if (elements.settingSttBackend) elements.settingSttBackend.value = data.CALLIO_STT_BACKEND || "whisper";
        if (elements.settingTtsBackend) elements.settingTtsBackend.value = data.CALLIO_TTS_BACKEND || "chatt";
        if (elements.settingHost) elements.settingHost.value = data.CALLIO_HOST || "0.0.0.0";
        if (elements.settingPort) elements.settingPort.value = data.CALLIO_PORT || "8000";
        applyProviderSpecificUI();
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

    function updateResumeLabel() {
        if (!elements.resumeLabel) return;
        if (!state.selectedSessionId) {
            elements.resumeLabel.textContent = "Current target session: Auto new session";
            return;
        }
        const shortId = state.selectedSessionId.slice(0, 8);
        elements.resumeLabel.textContent = `Current target session: ${shortId}`;
    }

    function setSelectedSession(sessionId) {
        state.selectedSessionId = sessionId || null;
        storeSessionId(state.selectedSessionId);
        updateResumeLabel();
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

    async function loadSetupSettings() {
        if (mode !== "web" || !elements.settingLlmProvider) return;
        try {
            const data = await requestJson("/api/v1/settings");
            fillSettingsForm(data.settings || {});
            state.settingsReady = Boolean(data.configured);
            storeSettingsReady(state.settingsReady);
            applySettingsReadyUI();
            setSaveSettingsStatus(state.settingsReady
                ? "Current settings look complete. Save again after making changes."
                : "Current settings are incomplete. Fill the required fields and save again.", state.settingsReady ? "success" : "warning");
            await loadOllamaModels();
        } catch (error) {
            console.warn("Failed to load setup settings", error);
            state.settingsReady = loadStoredSettingsReady();
            applySettingsReadyUI();
        }
    }

    async function saveSetupSettings() {
        if (mode !== "web") return;
        const payload = collectSettingsPayload();
        elements.saveSettingsBtn?.classList.add("is-loading");
        if (elements.saveSettingsBtn) {
            elements.saveSettingsBtn.disabled = true;
        }
        setSaveSettingsStatus("Saving settings to the server .env file...", "info");
        try {
            const data = await requestJson("/api/v1/settings", {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ settings: payload }),
            });
            state.settingsReady = Boolean(data.configured);
            storeSettingsReady(state.settingsReady);
            applySettingsReadyUI();
            if (state.settingsReady) {
                setSaveSettingsStatus("Settings saved successfully. Restart the service to fully apply provider-level changes.", "success");
                closeSettingsModal();
                showToast("Settings saved. You can start conversation now.", "success");
            } else {
                setSaveSettingsStatus(`Settings saved, but some required fields are still missing: ${(data.missing || []).join(", ") || "unknown fields"}.`, "warning");
                showToast(`Settings incomplete: ${(data.missing || []).join(", ") || "check required fields"}`, "warning", 5000);
            }
        } finally {
            elements.saveSettingsBtn?.classList.remove("is-loading");
            if (elements.saveSettingsBtn) {
                elements.saveSettingsBtn.disabled = false;
            }
        }
    }

    function renderSessions(items) {
        if (state.selectedSessionId && !items.some((s) => s.session_id === state.selectedSessionId)) {
            setSelectedSession(null);
        }
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
                setSelectedSession(session.session_id);
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
            if (elements.settingOllamaModelSearch) elements.settingOllamaModelSearch.value = data.CALLIO_LLM_MODEL || "";
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
                setSelectedSession(data.session_id);
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
        if (mode === "web" && !state.settingsReady) {
            openSettingsModal();
            showToast("Please finish setup wizard before starting conversation.", "warning", 4200);
            return;
        }
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
        elements.startBtn.disabled = mode === "web" ? !state.settingsReady : false;
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

    function bindTopNavigation() {
        document.querySelectorAll("[data-nav-target]").forEach((button) => {
            button.addEventListener("click", () => {
                const targetId = button.getAttribute("data-nav-target");
                const node = targetId ? document.getElementById(targetId) : null;
                if (node) {
                    node.scrollIntoView({ behavior: "smooth", block: "start" });
                }
            });
        });
    }

    function bindSettingsWizard() {
        if (mode !== "web") return;
        elements.settingLlmProvider?.addEventListener("change", async () => {
            applyProviderSpecificUI();
            await loadOllamaModels();
        });
        elements.settingOllamaBaseUrl?.addEventListener("change", async () => {
            await loadOllamaModels();
        });
        elements.settingOllamaModelSearch?.addEventListener("input", () => {
            const value = elements.settingOllamaModelSearch.value || "";
            if (value && elements.settingLlmModel) {
                elements.settingLlmModel.value = value;
            }
        });
        elements.refreshOllamaModelsBtn?.addEventListener("click", async () => {
            await loadOllamaModels();
        });
        document.querySelectorAll("#settingsModal input, #settingsModal select").forEach((node) => {
            node.addEventListener("input", () => {
                setSaveSettingsStatus("You have unsaved changes.", "info");
            });
            node.addEventListener("change", () => {
                setSaveSettingsStatus("You have unsaved changes.", "info");
            });
        });
        elements.openSettingsBtn?.addEventListener("click", openSettingsModal);
        elements.openSettingsInlineBtn?.addEventListener("click", openSettingsModal);
        elements.closeSettingsBtn?.addEventListener("click", closeSettingsModal);
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape" && elements.settingsModal && !elements.settingsModal.hidden) {
                closeSettingsModal();
            }
        });
        elements.settingsModal?.addEventListener("click", (event) => {
            if (event.target === elements.settingsModal) {
                closeSettingsModal();
            }
        });
        elements.saveSettingsBtn?.addEventListener("click", async () => {
            try {
                await saveSetupSettings();
            } catch (error) {
                showToast(`Save settings failed: ${error.message}`, "danger", 5000);
            }
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
    bindTopNavigation();
    bindSettingsWizard();
    loadSessionOptions();
    refreshSessionTasks();
    resetLiveReport();
    updateResumeLabel();
    applySettingsReadyUI();
    loadSetupSettings();

    if (mode === "mobile") {
        setStatus("warning", "Mobile ready", "Use HTTPS to enable microphone access.");
    } else {
        if (state.settingsReady) {
            setStatus("warning", "Disconnected", "Choose a previous session or start a new voice collaboration round.");
        }
    }
})();

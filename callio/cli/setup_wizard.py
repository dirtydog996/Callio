"""Interactive setup wizard for Callio.

Run:
    python -m callio setup
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import json
from pathlib import Path
from urllib.request import urlopen

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
_EXAMPLE_ENV_FILE = Path(__file__).resolve().parents[2] / ".env.example"

_CLOUD_COMPAT_PRESETS: dict[str, dict[str, str]] = {
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "api_key_env": "DEEPSEEK_API_KEY",
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
        "api_key_env": "DASHSCOPE_API_KEY",
    },
    "kimi": {
        "base_url": "https://api.moonshot.cn/v1",
        "model": "moonshot-v1-8k",
        "api_key_env": "MOONSHOT_API_KEY",
    },
    "custom": {
        "base_url": "",
        "model": "",
        "api_key_env": "CALLIO_LLM_API_KEY",
    },
}


def _print_header(text: str) -> None:
    width = 60
    print("\n" + "=" * width)
    print(f"  {text}")
    print("=" * width)


def _ask(prompt: str, default: str = "") -> str:
    hint = f" [{default}]" if default else ""
    answer = input(f"{prompt}{hint}: ").strip()
    return answer or default


def _ask_choice(prompt: str, choices: list[str], default: str) -> str:
    labels = "/".join(choices)
    while True:
        answer = _ask(f"{prompt} ({labels})", default)
        if answer in choices:
            return answer
        print(f"  Please choose one of: {labels}")


def _ask_bool(prompt: str, default: bool = False) -> bool:
    default_str = "y" if default else "n"
    answer = _ask(f"{prompt} (y/n)", default_str).lower()
    return answer in ("y", "yes", "1", "true")


def _check_package(package: str) -> bool:
    """Return True if the Python package can be imported."""
    import importlib.util

    spec = importlib.util.find_spec(package.replace("-", "_").split("[")[0])
    return spec is not None


def _install_package(package: str) -> bool:
    """Attempt to install *package* via pip. Returns True on success."""
    print(f"  Installing {package}...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", package],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        print(f"  ✅ {package} installed successfully.")
        return True
    print(f"  ❌ Failed to install {package}:\n{result.stderr[:500]}")
    return False


def _check_cli(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _ollama_tags_url(base_url: str) -> str:
    normalized = (base_url or "http://localhost:11434/v1").strip().rstrip("/")
    if normalized.endswith("/v1"):
        normalized = normalized[:-3]
    return f"{normalized}/api/tags"


def _fetch_ollama_models(base_url: str) -> tuple[list[str], str | None]:
    url = _ollama_tags_url(base_url)
    try:
        with urlopen(url, timeout=2.5) as response:  # nosec B310 - user-provided local/service URL
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return [], str(exc)
    models = payload.get("models", []) if isinstance(payload, dict) else []
    names = sorted({str(item.get("name", "")).strip() for item in models if isinstance(item, dict) and item.get("name")})
    return names, None


def _load_env_file(path: Path) -> dict[str, str]:
    """Parse a dotenv-style file into a dict."""
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def _load_existing_env() -> dict[str, str]:
    """Load defaults from .env.example and override with .env if present."""
    env = _load_env_file(_EXAMPLE_ENV_FILE)
    env.update(_load_env_file(_ENV_FILE))
    return env


def _guess_llm_mode(config: dict[str, str]) -> str:
    provider = (config.get("CALLIO_LLM_PROVIDER", "ollama") or "ollama").strip().lower()
    return "local" if provider == "ollama" else "cloud"


def _guess_cloud_vendor(config: dict[str, str]) -> str:
    provider = (config.get("CALLIO_LLM_PROVIDER", "") or "").strip().lower()
    if provider in {"openai", "anthropic", "gemini", "deepseek", "qwen", "kimi"}:
        return provider
    if provider != "openai_compatible":
        return "custom"

    base_url = (config.get("CALLIO_LLM_BASE_URL", "") or "").strip().lower()
    if "deepseek" in base_url:
        return "deepseek"
    if "dashscope" in base_url or "aliyuncs" in base_url or "qwen" in base_url:
        return "qwen"
    if "moonshot" in base_url or "kimi" in base_url:
        return "kimi"
    return "custom"


def _setup_llm(config: dict[str, str]) -> None:
    _print_header("LLM Provider Configuration")
    print("Choose local (Ollama) or cloud (OpenAI/DeepSeek/Qwen/Kimi/...).\n")

    llm_mode = _ask_choice(
        "LLM mode",
        ["local", "cloud"],
        _guess_llm_mode(config),
    )

    if llm_mode == "local":
        provider = "ollama"
        config["CALLIO_LLM_PROVIDER"] = provider
        if _check_cli("ollama"):
            print("  ✅ ollama found on PATH.")
        else:
            print("  ⚠️  ollama not found. Install from https://ollama.com or run:")
            print("       curl -fsSL https://ollama.com/install.sh | sh")
            if _ask_bool("  Attempt to install ollama now?", default=False):
                subprocess.run(
                    ["sh", "-c", "curl -fsSL https://ollama.com/install.sh | sh"],
                    check=False,
                )
        base_url = _ask(
            "Ollama base URL",
            config.get("CALLIO_OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        )
        config["CALLIO_OLLAMA_BASE_URL"] = base_url
        config.pop("CALLIO_LLM_BASE_URL", None)

        discovered_models: list[str] = []
        discovery_error: str | None = None
        discovered_models, discovery_error = _fetch_ollama_models(base_url)
        if discovered_models:
            print(f"  ✅ Found {len(discovered_models)} installed Ollama model(s).")
            print(f"     Example: {', '.join(discovered_models[:5])}")
        else:
            print("  ⚠️  Could not auto-detect installed Ollama models from the configured base URL.")
            if discovery_error:
                print(f"     Reason: {discovery_error}")

        default_model = config.get("CALLIO_LLM_MODEL", "qwen2.5:7b")
        if discovered_models and default_model not in discovered_models:
            default_model = discovered_models[0]

        while True:
            model = _ask("LLM model name", default_model)
            if not discovered_models or model in discovered_models:
                config["CALLIO_LLM_MODEL"] = model
                break

            print(f"  ⚠️  Model '{model}' is not in the installed Ollama model list.")
            print("     If you meant a hosted model (e.g. DeepSeek cloud names), use provider 'openai_compatible' instead of 'ollama'.")
            if _ask_bool("  Keep this model name anyway?", default=False):
                config["CALLIO_LLM_MODEL"] = model
                break

        if _check_cli("ollama") and model and _ask_bool("  Pull this Ollama model now?", default=False):
            subprocess.run(["ollama", "pull", model], check=False)

        return

    cloud_vendor = _ask_choice(
        "Cloud vendor",
        ["openai", "deepseek", "qwen", "kimi", "anthropic", "gemini", "custom"],
        _guess_cloud_vendor(config),
    )

    if cloud_vendor == "openai":
        config["CALLIO_LLM_PROVIDER"] = "openai"
        config.pop("CALLIO_LLM_BASE_URL", None)
        api_key = _ask("OpenAI API key (OPENAI_API_KEY)", config.get("CALLIO_LLM_API_KEY", ""))
        config["CALLIO_LLM_API_KEY"] = api_key
        model = _ask("Model name", config.get("CALLIO_LLM_MODEL", "gpt-4o"))
        config["CALLIO_LLM_MODEL"] = model
        return

    if cloud_vendor == "anthropic":
        config["CALLIO_LLM_PROVIDER"] = "anthropic"
        config.pop("CALLIO_LLM_BASE_URL", None)
        api_key = _ask("Anthropic API key", config.get("CALLIO_LLM_API_KEY", ""))
        config["CALLIO_LLM_API_KEY"] = api_key
        model = _ask("Model name", config.get("CALLIO_LLM_MODEL", "claude-3-5-sonnet-20241022"))
        config["CALLIO_LLM_MODEL"] = model
        return

    if cloud_vendor == "gemini":
        config["CALLIO_LLM_PROVIDER"] = "gemini"
        config.pop("CALLIO_LLM_BASE_URL", None)
        api_key = _ask("Gemini API key", config.get("CALLIO_LLM_API_KEY", ""))
        config["CALLIO_LLM_API_KEY"] = api_key
        model = _ask("Model name", config.get("CALLIO_LLM_MODEL", "gemini-1.5-pro"))
        config["CALLIO_LLM_MODEL"] = model
        return

    # deepseek/qwen/kimi/custom share the OpenAI-compatible transport.
    # Keep deepseek/qwen/kimi as first-class provider values for clarity.
    config["CALLIO_LLM_PROVIDER"] = cloud_vendor if cloud_vendor in {"deepseek", "qwen", "kimi"} else "openai_compatible"
    preset = _CLOUD_COMPAT_PRESETS.get(cloud_vendor, _CLOUD_COMPAT_PRESETS["custom"])
    default_base = config.get("CALLIO_LLM_BASE_URL", "") or preset["base_url"]
    default_model = config.get("CALLIO_LLM_MODEL", "") or preset["model"]
    base_url = _ask("API base URL", default_base)
    config["CALLIO_LLM_BASE_URL"] = base_url
    api_key_prompt = f"API key ({preset['api_key_env']} or CALLIO_LLM_API_KEY)"
    api_key = _ask(api_key_prompt, config.get("CALLIO_LLM_API_KEY", ""))
    config["CALLIO_LLM_API_KEY"] = api_key
    model = _ask("Model name", default_model)
    config["CALLIO_LLM_MODEL"] = model


def _setup_stt(config: dict[str, str]) -> None:
    _print_header("Speech-to-Text (STT) Configuration")
    print("Backends: whisper (default, uses faster-whisper), sensevoice (FunASR/SenseVoice)\n")

    backend = _ask_choice(
        "STT backend",
        ["whisper", "sensevoice"],
        config.get("CALLIO_STT_BACKEND", "whisper"),
    )
    config["CALLIO_STT_BACKEND"] = backend

    if backend == "whisper":
        if _check_package("faster_whisper"):
            print("  ✅ faster-whisper is installed.")
        else:
            print("  ⚠️  faster-whisper not found.")
            if _ask_bool("  Install faster-whisper now?", default=True):
                _install_package("faster-whisper")
        model = _ask(
            "Whisper model (tiny/base/small/medium/large-v3)",
            config.get("CALLIO_WHISPER_MODEL", "base"),
        )
        config["CALLIO_WHISPER_MODEL"] = model
        device = _ask_choice("Device", ["cpu", "cuda"], config.get("CALLIO_WHISPER_DEVICE", "cpu"))
        config["CALLIO_WHISPER_DEVICE"] = device

    elif backend == "sensevoice":
        for pkg in ("funasr", "modelscope"):
            if _check_package(pkg):
                print(f"  ✅ {pkg} is installed.")
            else:
                print(f"  ⚠️  {pkg} not found.")
                if _ask_bool(f"  Install {pkg} now?", default=True):
                    _install_package(pkg)
        model = _ask(
            "FunASR model",
            config.get("CALLIO_FUNASR_MODEL", "iic/SenseVoiceSmall"),
        )
        config["CALLIO_FUNASR_MODEL"] = model


def _setup_tts(config: dict[str, str]) -> None:
    _print_header("Text-to-Speech (TTS) Configuration")
    print("Backends: chatt (ChatTTS, default), say (macOS only), edge (EdgeTTS), cosyvoice, fish\n")

    backend = _ask_choice(
        "TTS backend",
        ["chatt", "say", "edge", "cosyvoice", "fish"],
        config.get("CALLIO_TTS_BACKEND", "chatt"),
    )
    config["CALLIO_TTS_BACKEND"] = backend

    if backend == "chatt":
        for pkg in ("ChatTTS", "transformers"):
            display = pkg
            check_name = pkg.lower()
            if _check_package(check_name) or _check_package(pkg):
                print(f"  ✅ {display} is installed.")
            else:
                print(f"  ⚠️  {display} not found.")
                if pkg == "transformers":
                    if _ask_bool("  Install transformers>=4.41,<5 now?", default=True):
                        _install_package("transformers>=4.41,<5")
                else:
                    if _ask_bool(f"  Install {display} now?", default=True):
                        _install_package(display)
        hf_endpoint = _ask(
            "HuggingFace mirror endpoint (leave blank for default)",
            config.get("CALLIO_HF_ENDPOINT", ""),
        )
        if hf_endpoint:
            config["CALLIO_HF_ENDPOINT"] = hf_endpoint
        else:
            config.pop("CALLIO_HF_ENDPOINT", None)

    elif backend == "say":
        if not _check_cli("say"):
            print("  ⚠️  'say' command not found — this backend requires macOS.")

    elif backend == "edge":
        if _check_package("edge_tts"):
            print("  ✅ edge-tts is installed.")
        else:
            print("  ⚠️  edge-tts not found.")
            if _ask_bool("  Install edge-tts now?", default=True):
                _install_package("edge-tts")
        if not _check_cli("ffmpeg"):
            print("  ⚠️  ffmpeg not found on PATH. EdgeTTS requires ffmpeg for PCM conversion.")
            print("      Install: brew install ffmpeg  /  apt-get install ffmpeg")
        voice = _ask("EdgeTTS voice", config.get("CALLIO_EDGE_TTS_VOICE", "zh-CN-XiaoxiaoNeural"))
        config["CALLIO_EDGE_TTS_VOICE"] = voice

    elif backend == "cosyvoice":
        url = _ask("CosyVoice server URL", config.get("CALLIO_COSYVOICE_URL", "http://localhost:9880"))
        config["CALLIO_COSYVOICE_URL"] = url

    elif backend == "fish":
        url = _ask("Fish Speech server URL", config.get("CALLIO_FISH_SPEECH_URL", "http://localhost:8080"))
        config["CALLIO_FISH_SPEECH_URL"] = url


def _setup_notifications(config: dict[str, str]) -> None:
    _print_header("Notification Webhooks (optional)")
    print("Callio can send a message when a voice session ends.\n")

    enable = _ask_bool(
        "Enable notifications?",
        default=bool(
            config.get("CALLIO_NOTIFY_DISCORD_WEBHOOK")
            or config.get("CALLIO_NOTIFY_WECHAT_WEBHOOK")
            or config.get("CALLIO_NOTIFY_FEISHU_WEBHOOK")
            or config.get("CALLIO_NOTIFY_TELEGRAM_WEBHOOK")
        ),
    )
    if not enable:
        return

    channels = [
        ("Discord", "CALLIO_NOTIFY_DISCORD_WEBHOOK"),
        ("WeChat Work", "CALLIO_NOTIFY_WECHAT_WEBHOOK"),
        ("Feishu / Lark", "CALLIO_NOTIFY_FEISHU_WEBHOOK"),
        ("Telegram", "CALLIO_NOTIFY_TELEGRAM_WEBHOOK"),
    ]
    for label, key in channels:
        url = _ask(f"  {label} webhook URL (leave blank to skip)", config.get(key, ""))
        if url:
            config[key] = url
        else:
            config.pop(key, None)


def _setup_server(config: dict[str, str]) -> None:
    _print_header("Server Configuration")

    port = _ask("Server port", config.get("CALLIO_PORT", "8000"))
    config["CALLIO_PORT"] = port

    host = _ask("Bind host", config.get("CALLIO_HOST", "0.0.0.0"))
    config["CALLIO_HOST"] = host

    use_https = _ask_bool(
        "Enable HTTPS?",
        default=bool(config.get("CALLIO_SSL_CERT") and config.get("CALLIO_SSL_KEY")),
    )
    if use_https:
        cert = _ask("SSL certificate path (PEM)", config.get("CALLIO_SSL_CERT", ""))
        key = _ask("SSL key path (PEM)", config.get("CALLIO_SSL_KEY", ""))
        config["CALLIO_SSL_CERT"] = cert
        config["CALLIO_SSL_KEY"] = key
    else:
        config.pop("CALLIO_SSL_CERT", None)
        config.pop("CALLIO_SSL_KEY", None)

    log_level = _ask_choice(
        "Log level",
        ["DEBUG", "INFO", "WARNING", "ERROR"],
        config.get("CALLIO_LOG_LEVEL", "INFO"),
    )
    config["CALLIO_LOG_LEVEL"] = log_level


def _setup_runtime(config: dict[str, str]) -> None:
    _print_header("Runtime / Worker Configuration")

    agent_backend = _ask_choice(
        "Agent backend",
        ["auto", "hermes", "openclaw", "goose", "aider", "claude"],
        config.get("CALLIO_AGENT_BACKEND", "auto") or "auto",
    )
    if agent_backend != "auto":
        config["CALLIO_AGENT_BACKEND"] = agent_backend
    else:
        config.pop("CALLIO_AGENT_BACKEND", None)

    agent_command = _ask(
        "Custom agent command (optional, must include {task})",
        config.get("CALLIO_AGENT_COMMAND", ""),
    )
    if agent_command:
        config["CALLIO_AGENT_COMMAND"] = agent_command
    else:
        config.pop("CALLIO_AGENT_COMMAND", None)

    config["CALLIO_WHISPER_PRELOAD"] = "1" if _ask_bool(
        "Preload Whisper model at startup?",
        default=config.get("CALLIO_WHISPER_PRELOAD", "1") == "1",
    ) else "0"
    config["CALLIO_TTS_PRELOAD"] = "1" if _ask_bool(
        "Preload TTS backend at startup?",
        default=config.get("CALLIO_TTS_PRELOAD", "1") == "1",
    ) else "0"
    config["CALLIO_REQUIRE_VERBAL_CONFIRM"] = "1" if _ask_bool(
        "Require verbal confirmation before execute?",
        default=config.get("CALLIO_REQUIRE_VERBAL_CONFIRM", "1") == "1",
    ) else "0"

    config["CALLIO_VAD_STOP_SECS"] = _ask(
        "VAD stop silence seconds",
        config.get("CALLIO_VAD_STOP_SECS", "0.4"),
    )
    config["CALLIO_NOTIFY_TIMEOUT_SEC"] = _ask(
        "Notification timeout seconds",
        config.get("CALLIO_NOTIFY_TIMEOUT_SEC", "8"),
    )
    config["CALLIO_MAX_PARALLEL_TASKS"] = _ask(
        "Max parallel tasks per session",
        config.get("CALLIO_MAX_PARALLEL_TASKS", "3"),
    )
    config["CALLIO_GLOBAL_MAX_PARALLEL"] = _ask(
        "Global max parallel tasks",
        config.get("CALLIO_GLOBAL_MAX_PARALLEL", "5"),
    )
    config["CALLIO_TASK_TIMEOUT_SEC"] = _ask(
        "Task timeout seconds",
        config.get("CALLIO_TASK_TIMEOUT_SEC", "3600"),
    )
    config["CALLIO_EXECUTE_MAX_RETRIES"] = _ask(
        "Task execute max retries",
        config.get("CALLIO_EXECUTE_MAX_RETRIES", "3"),
    )
    config["CALLIO_SUMMARIZE_DEBOUNCE_SEC"] = _ask(
        "Summarize debounce seconds",
        config.get("CALLIO_SUMMARIZE_DEBOUNCE_SEC", "30"),
    )
    config["CALLIO_SANDBOX_ROOT"] = _ask(
        "Sandbox root path",
        config.get("CALLIO_SANDBOX_ROOT", str(Path.cwd())),
    )


def _write_env(config: dict[str, str]) -> None:
    lines = ["# Callio configuration — generated by `callio setup`", ""]
    for key, value in sorted(config.items()):
        if value:
            lines.append(f"{key}={value}")
    _ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n✅ Configuration saved to {_ENV_FILE}")


def _is_sensitive_config_key(key: str) -> bool:
    upper = key.upper()
    return any(token in upper for token in ("KEY", "WEBHOOK", "TOKEN", "SECRET", "PASSWORD"))


def _print_summary(config: dict[str, str]) -> None:
    rows = [
        ("LLM provider", config.get("CALLIO_LLM_PROVIDER", "")),
        ("LLM model", config.get("CALLIO_LLM_MODEL", "")),
        ("LLM base URL", config.get("CALLIO_LLM_BASE_URL", "")),
        ("Ollama URL", config.get("CALLIO_OLLAMA_BASE_URL", "")),
        ("STT backend", config.get("CALLIO_STT_BACKEND", "")),
        ("Whisper model", config.get("CALLIO_WHISPER_MODEL", "")),
        ("Whisper device", config.get("CALLIO_WHISPER_DEVICE", "")),
        ("Whisper preload", config.get("CALLIO_WHISPER_PRELOAD", "")),
        ("FunASR model", config.get("CALLIO_FUNASR_MODEL", "")),
        ("TTS backend", config.get("CALLIO_TTS_BACKEND", "")),
        ("TTS preload", config.get("CALLIO_TTS_PRELOAD", "")),
        ("HF endpoint", config.get("CALLIO_HF_ENDPOINT", "")),
        ("Edge voice", config.get("CALLIO_EDGE_TTS_VOICE", "")),
        ("CosyVoice URL", config.get("CALLIO_COSYVOICE_URL", "")),
        ("Fish Speech URL", config.get("CALLIO_FISH_SPEECH_URL", "")),
        ("Agent backend", config.get("CALLIO_AGENT_BACKEND", "")),
        ("Task timeout", config.get("CALLIO_TASK_TIMEOUT_SEC", "")),
        ("Global parallel", config.get("CALLIO_GLOBAL_MAX_PARALLEL", "")),
        ("VAD stop secs", config.get("CALLIO_VAD_STOP_SECS", "")),
        ("Host", config.get("CALLIO_HOST", "")),
        ("Port", config.get("CALLIO_PORT", "")),
        ("Log level", config.get("CALLIO_LOG_LEVEL", "")),
    ]
    for label, value in rows:
        print(f"  {label} = {value or '(not set)'}")

    notifications_enabled = any(
        config.get(key)
        for key in (
            "CALLIO_NOTIFY_DISCORD_WEBHOOK",
            "CALLIO_NOTIFY_WECHAT_WEBHOOK",
            "CALLIO_NOTIFY_FEISHU_WEBHOOK",
            "CALLIO_NOTIFY_TELEGRAM_WEBHOOK",
        )
    )
    print(f"  Notifications = {'enabled' if notifications_enabled else 'disabled'}")
    https_enabled = bool(config.get("CALLIO_SSL_CERT") and config.get("CALLIO_SSL_KEY"))
    print(f"  HTTPS = {'configured' if https_enabled else 'disabled'}")


def run_setup_wizard() -> None:
    print("\n" + "=" * 60)
    print("  Callio Setup Wizard")
    print("=" * 60)

    config = _load_existing_env()
    if config:
        print(f"\n  Found existing configuration in {_ENV_FILE}")
        if not _ask_bool("  Update it?", default=True):
            print("  Aborted — existing configuration unchanged.")
            return

    configure_runtime = _ask_bool(
        "Configure runtime/worker advanced options too?",
        default=True,
    )

    _setup_llm(config)
    _setup_stt(config)
    _setup_tts(config)
    _setup_notifications(config)
    _setup_server(config)
    if configure_runtime:
        _setup_runtime(config)

    _print_header("Summary")
    _print_summary(config)

    print()
    if _ask_bool("Save this configuration?", default=True):
        _write_env(config)
        print("\n  Run `python -m callio` to start the server.")
    else:
        print("  Aborted — nothing was saved.")

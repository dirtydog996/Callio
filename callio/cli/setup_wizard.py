"""Interactive setup wizard for Callio.

Run:
    python -m callio setup
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


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


def _load_existing_env() -> dict[str, str]:
    """Parse an existing .env file into a dict."""
    env: dict[str, str] = {}
    if _ENV_FILE.exists():
        for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def _setup_llm(config: dict[str, str]) -> None:
    _print_header("LLM Provider Configuration")
    print("Supported providers: ollama (local), openai, anthropic, gemini, openai_compatible\n")

    provider = _ask_choice(
        "LLM provider",
        ["ollama", "openai", "anthropic", "gemini", "openai_compatible"],
        config.get("CALLIO_LLM_PROVIDER", "ollama"),
    )
    config["CALLIO_LLM_PROVIDER"] = provider

    if provider == "ollama":
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
        model = _ask("LLM model name", config.get("CALLIO_LLM_MODEL", "qwen2.5:7b"))
        config["CALLIO_LLM_MODEL"] = model

    elif provider == "openai":
        api_key = _ask("OpenAI API key (OPENAI_API_KEY)", config.get("CALLIO_LLM_API_KEY", ""))
        config["CALLIO_LLM_API_KEY"] = api_key
        model = _ask("Model name", config.get("CALLIO_LLM_MODEL", "gpt-4o"))
        config["CALLIO_LLM_MODEL"] = model

    elif provider == "anthropic":
        api_key = _ask("Anthropic API key", config.get("CALLIO_LLM_API_KEY", ""))
        config["CALLIO_LLM_API_KEY"] = api_key
        model = _ask("Model name", config.get("CALLIO_LLM_MODEL", "claude-3-5-sonnet-20241022"))
        config["CALLIO_LLM_MODEL"] = model

    elif provider == "gemini":
        api_key = _ask("Gemini API key", config.get("CALLIO_LLM_API_KEY", ""))
        config["CALLIO_LLM_API_KEY"] = api_key
        model = _ask("Model name", config.get("CALLIO_LLM_MODEL", "gemini-1.5-pro"))
        config["CALLIO_LLM_MODEL"] = model

    elif provider == "openai_compatible":
        base_url = _ask("API base URL", config.get("CALLIO_LLM_BASE_URL", ""))
        config["CALLIO_LLM_BASE_URL"] = base_url
        api_key = _ask("API key", config.get("CALLIO_LLM_API_KEY", ""))
        config["CALLIO_LLM_API_KEY"] = api_key
        model = _ask("Model name", config.get("CALLIO_LLM_MODEL", ""))
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
        ("STT backend", config.get("CALLIO_STT_BACKEND", "")),
        ("Whisper model", config.get("CALLIO_WHISPER_MODEL", "")),
        ("Whisper device", config.get("CALLIO_WHISPER_DEVICE", "")),
        ("FunASR model", config.get("CALLIO_FUNASR_MODEL", "")),
        ("TTS backend", config.get("CALLIO_TTS_BACKEND", "")),
        ("HF endpoint", config.get("CALLIO_HF_ENDPOINT", "")),
        ("Edge voice", config.get("CALLIO_EDGE_TTS_VOICE", "")),
        ("CosyVoice URL", config.get("CALLIO_COSYVOICE_URL", "")),
        ("Fish Speech URL", config.get("CALLIO_FISH_SPEECH_URL", "")),
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

    _setup_llm(config)
    _setup_stt(config)
    _setup_tts(config)
    _setup_notifications(config)
    _setup_server(config)

    _print_header("Summary")
    _print_summary(config)

    print()
    if _ask_bool("Save this configuration?", default=True):
        _write_env(config)
        print("\n  Run `python -m callio` to start the server.")
    else:
        print("  Aborted — nothing was saved.")

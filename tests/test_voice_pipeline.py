"""Unit tests for callio.voice.pipeline helper functions."""
from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

for _stub in ("openai", "chromadb"):
    if _stub not in sys.modules:
        _m = MagicMock()
        _m.__spec__ = None
        sys.modules[_stub] = _m


def _ensure_stub_pkg(fullname: str):
    if fullname not in sys.modules or not hasattr(sys.modules[fullname], "__path__"):
        mod = types.ModuleType(fullname)
        mod.__path__ = []
        mod.__spec__ = None
        mod.__package__ = fullname
        sys.modules[fullname] = mod
    return sys.modules[fullname]


for _pkg in ("fastapi", "starlette", "starlette.websockets"):
    _ensure_stub_pkg(_pkg)

_fastapi_mod = sys.modules["fastapi"]
for _attr in ("FastAPI", "WebSocket"):
    if not hasattr(_fastapi_mod, _attr):
        setattr(_fastapi_mod, _attr, type(_attr, (), {"__init__": lambda self, *a, **kw: None}))
_starlette_ws_mod = sys.modules["starlette.websockets"]
if not hasattr(_starlette_ws_mod, "WebSocketDisconnect"):
    _starlette_ws_mod.WebSocketDisconnect = type("WebSocketDisconnect", (), {})

_openai = sys.modules["openai"]
if not hasattr(_openai, "AsyncOpenAI"):
    _openai.AsyncOpenAI = MagicMock()


def _make_pipecat_stub(fullname: str) -> types.ModuleType:
    mod = types.ModuleType(fullname)
    mod.__path__ = []
    mod.__spec__ = None
    mod.__package__ = fullname
    for attr in ("Frame", "InterruptionFrame", "TextFrame", "TranscriptionFrame",
                  "TTSTextFrame", "ErrorFrame", "InputAudioRawFrame",
                  "OutputAudioRawFrame", "StartFrame", "VADUserStartedSpeakingFrame",
                  "FrameDirection", "FrameProcessor", "Pipeline", "PipelineTask",
                  "WorkerRunner", "LLMContext", "LLMContextAggregatorPair",
                  "VADProcessor", "FrameSerializer", "SileroVADAnalyzer",
                  "VADParams", "FastAPIWebsocketParams", "FastAPIWebsocketTransport",
                  "OLLamaLLMService", "OllamaLLMSettings", "Language",
                  "FunctionSchema", "ToolsSchema", "TTSSettings", "TTSService", "FastAPI"):
        setattr(mod, attr, type(attr, (), {"__init__": lambda self, *a, **kw: None}))
    return mod


for _name in ("pipecat", "pipecat.frames", "pipecat.frames.frames",
              "pipecat.processors", "pipecat.processors.frame_processor",
              "pipecat.pipeline", "pipecat.pipeline.pipeline", "pipecat.pipeline.task",
              "pipecat.workers", "pipecat.workers.runner",
              "pipecat.processors.aggregators", "pipecat.processors.aggregators.llm_context",
              "pipecat.processors.aggregators.llm_response_universal",
              "pipecat.processors.audio", "pipecat.processors.audio.vad_processor",
              "pipecat.adapters", "pipecat.adapters.schemas",
              "pipecat.adapters.schemas.function_schema", "pipecat.adapters.schemas.tools_schema",
              "pipecat.audio", "pipecat.audio.vad", "pipecat.audio.vad.silero",
              "pipecat.audio.vad.vad_analyzer",
              "pipecat.transcriptions", "pipecat.transcriptions.language",
              "pipecat.transports", "pipecat.transports.websocket",
              "pipecat.transports.websocket.fastapi",
              "pipecat.services", "pipecat.services.ollama",
              "pipecat.services.ollama.llm", "pipecat.services.settings",
              "pipecat.services.tts_service",
              "pipecat.serializers", "pipecat.serializers.base_serializer"):
    sys.modules[_name] = _make_pipecat_stub(_name)

_voice_pkg = MagicMock()
_voice_pkg.__path__ = [str(pathlib.Path(__file__).parent.parent / "callio" / "voice")]
_voice_pkg.__package__ = "callio.voice"
sys.modules["callio.voice"] = _voice_pkg


def _load_voice_mod(name: str):
    base = pathlib.Path(__file__).parent.parent / "callio" / "voice"
    file_path = base / name.replace(".", "/")
    if file_path.is_dir():
        file_path = file_path / "__init__.py"
    else:
        file_path = file_path.with_suffix(".py")
    spec = importlib.util.spec_from_file_location(f"callio.voice.{name}", file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"callio.voice.{name}"] = mod
    spec.loader.exec_module(mod)
    return mod


_IMPORTS_OK = False
try:
    _load_voice_mod("prompt")
    _load_voice_mod("resume_context")
    _load_voice_mod("memory_context")
    _load_voice_mod("session_hook")
    _load_voice_mod("notifier")
    _load_voice_mod("tts_loader")
    _load_voice_mod("web_tts")
    _load_voice_mod("whisper_loader")
    _load_voice_mod("funasr_loader")
    _load_voice_mod("tools.schemas")
    _load_voice_mod("tools.handlers")

    _base = pathlib.Path(__file__).parent.parent / "callio" / "voice" / "pipeline.py"
    _spec = importlib.util.spec_from_file_location("callio.voice.pipeline", _base)
    _pipeline = importlib.util.module_from_spec(_spec)
    sys.modules["callio.voice.pipeline"] = _pipeline
    _spec.loader.exec_module(_pipeline)
    _IMPORTS_OK = True
except Exception:
    _IMPORTS_OK = False


@unittest.skipUnless(_IMPORTS_OK, "voice pipeline not importable")
class TestSummarizeVoiceError(unittest.TestCase):
    def test_tools_not_supported(self):
        title, detail = _pipeline._summarize_voice_error("model does not support tools")
        self.assertEqual(title, "Model does not support tool calling")
        self.assertIn("tools-capable", detail)

    def test_model_not_found(self):
        title, detail = _pipeline._summarize_voice_error("Error: model not found, try pulling it first")
        self.assertEqual(title, "Model not found")
        self.assertIn("not installed", detail)

    def test_connection_refused(self):
        title, detail = _pipeline._summarize_voice_error("connection refused on port 11434")
        self.assertEqual(title, "LLM service unreachable")
        self.assertIn("Ollama", detail)

    def test_timed_out(self):
        title, detail = _pipeline._summarize_voice_error("Request timed out after 30s")
        self.assertEqual(title, "LLM service unreachable")
        self.assertIn("reachable", detail)

    def test_generic_error(self):
        title, detail = _pipeline._summarize_voice_error("some unexpected error")
        self.assertEqual(title, "Voice request failed")
        self.assertIn("provider", detail)

    def test_empty_message(self):
        title, _ = _pipeline._summarize_voice_error("")
        self.assertEqual(title, "Voice request failed")

    def test_none_message(self):
        title, _ = _pipeline._summarize_voice_error(None)
        self.assertEqual(title, "Voice request failed")


@unittest.skipUnless(_IMPORTS_OK, "voice pipeline not importable")
class TestOnUserSpeechStart(unittest.TestCase):
    def test_calls_send_control_message(self):
        transport = MagicMock()
        transport.send_control_message = AsyncMock()
        pipeline = MagicMock()
        asyncio.run(_pipeline.on_user_speech_start(transport, pipeline))
        transport.send_control_message.assert_called_once_with({"action": "mute_tts"})
        pipeline.clear_buffers.assert_called_once()
        pipeline.cancel_current_task.assert_called_once()

    def test_missing_methods_do_not_raise(self):
        transport = MagicMock(spec=[])
        pipeline = MagicMock(spec=[])
        asyncio.run(_pipeline.on_user_speech_start(transport, pipeline))


@unittest.skipUnless(_IMPORTS_OK, "voice pipeline not importable")
class TestCreateSTT(unittest.TestCase):
    def test_whisper_backend(self):
        settings = MagicMock()
        settings.stt_backend = "whisper"
        with patch.object(_pipeline, "create_whisper_stt", return_value="whisper_stt") as mock_stt:
            result = _pipeline._create_stt(settings)
            self.assertEqual(result, "whisper_stt")
            mock_stt.assert_called_once_with(settings)

    def test_sensevoice_backend(self):
        settings = MagicMock()
        settings.stt_backend = "sensevoice"
        with patch.object(sys.modules["callio.voice.funasr_loader"], "create_sensevoice_stt", return_value="sense_stt"):
            result = _pipeline._create_stt(settings)
            self.assertEqual(result, "sense_stt")

    def test_default_backend_is_whisper(self):
        settings = MagicMock()
        settings.stt_backend = None
        with patch.object(_pipeline, "create_whisper_stt", return_value="default_stt"):
            result = _pipeline._create_stt(settings)
            self.assertEqual(result, "default_stt")


if __name__ == "__main__":
    unittest.main()

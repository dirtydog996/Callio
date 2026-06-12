from __future__ import annotations

import asyncio
import subprocess
from typing import Any, AsyncGenerator

from fastapi import FastAPI, WebSocket

from callio.config.settings import Settings, get_settings
from callio.voice.actions import hermes_tool_definition
from callio.voice.prompt import build_system_prompt


async def on_user_speech_start(transport: Any, pipeline: Any) -> None:
    if hasattr(transport, "send_control_message"):
        await transport.send_control_message({"action": "mute_tts"})
    if hasattr(pipeline, "clear_buffers"):
        pipeline.clear_buffers()
    if hasattr(pipeline, "cancel_current_task"):
        pipeline.cancel_current_task()


async def execute_hermes_coding(params: Any) -> None:
    arguments = getattr(params, "arguments", {})
    summary = arguments.get("summary", "")
    actions = arguments.get("actions", [])
    hermes_prompt = (
        f"【本地语音脑暴结论】：{summary}\n"
        f"【请立即执行以下 Action 清单】：\n" + "\n".join(f"- {action}" for action in actions)
    )

    try:
        process = await asyncio.create_subprocess_exec(
            "hermes",
            "run",
            "--task",
            hermes_prompt,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        asyncio.create_task(monitor_hermes(process))
        message = "Hermes 已经在后台启动。"
    except Exception as exc:  # pragma: no cover - depends on local runtime
        message = f"唤醒 Hermes 失败: {exc}"

    await params.result_callback({"status": "triggered", "message": message})


async def monitor_hermes(process: asyncio.subprocess.Process) -> None:
    await process.communicate()


class FallbackMacNativeTTSService:
    def __init__(self) -> None:
        self._engine = None
        try:
            import pyttsx3

            try:
                self._engine = pyttsx3.init(driverName="nsss")
            except Exception:
                self._engine = pyttsx3.init()
            voices = self._engine.getProperty("voices")
            for voice in voices:
                languages = getattr(voice, "languages", [])
                if any("zh" in str(language) for language in languages) or "CN" in getattr(voice, "id", ""):
                    self._engine.setProperty("voice", voice.id)
                    break
            self._engine.setProperty("rate", 175)
        except Exception:
            self._engine = None

    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Any | None, None]:
        if self._engine is not None:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._speak, text)
        yield None

    def _speak(self, text: str) -> None:
        if self._engine is None:
            return
        self._engine.say(text)
        self._engine.runAndWait()


def register_voice_routes(app: FastAPI, settings: Settings | None = None) -> None:
    settings = settings or get_settings()

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        try:
            from pipecat.adapters.schemas.function_schema import FunctionSchema
            from pipecat.adapters.schemas.tools_schema import ToolsSchema
            from pipecat.pipeline.pipeline import Pipeline
            from pipecat.pipeline.runner import PipelineRunner
            from pipecat.pipeline.task import PipelineTask
            from pipecat.processors.aggregators.llm_context import LLMContext
            from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
            from pipecat.services.llm_service import FunctionCallParams
            from pipecat.services.ollama.llm import OLLamaLLMService
            from pipecat.services.tts_service import TTSService
            from pipecat.services.whisper.stt import WhisperSTTService
            from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams, FastAPIWebsocketTransport
        except Exception:
            await websocket.accept()
            await websocket.send_json({
                "type": "assistant",
                "text": "语音依赖未安装，状态与任务接口已可用。",
            })
            await websocket.close()
            return

        class MacNativeTTSService(TTSService):
            def __init__(self) -> None:
                super().__init__(push_stop_frames=True, sample_rate=22050)
                self._delegate = FallbackMacNativeTTSService()

            async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Any | None, None]:
                async for frame in self._delegate.run_tts(text, context_id):
                    yield frame

        async def execute_tool(params: FunctionCallParams) -> None:
            await execute_hermes_coding(params)

        transport = FastAPIWebsocketTransport(
            websocket,
            FastAPIWebsocketParams(audio_in_enabled=True, audio_out_enabled=True),
        )
        stt = WhisperSTTService(model=settings.whisper_model, device="cpu")
        llm = OLLamaLLMService(base_url=settings.ollama_base_url, model=settings.llm_model)
        tts = MacNativeTTSService()
        tool_def = hermes_tool_definition()
        hermes_schema = FunctionSchema(
            name=tool_def["name"],
            description=tool_def["description"],
            properties=tool_def["properties"],
            required=tool_def["required"],
        )
        llm.register_function("execute_hermes_coding", execute_tool, cancel_on_interruption=False)
        context = LLMContext(
            messages=[{"role": "system", "content": build_system_prompt(settings.voice_response_limit)}],
            tools=ToolsSchema(standard_tools=[hermes_schema]),
        )
        context_aggregator = LLMContextAggregatorPair(context)
        pipeline = Pipeline([
            transport.input(),
            stt,
            context_aggregator.user(),
            llm,
            tts,
            transport.output(),
            context_aggregator.assistant(),
        ])
        task = PipelineTask(pipeline)
        runner = PipelineRunner()
        await runner.run(task)

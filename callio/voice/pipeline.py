from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from fastapi import FastAPI, WebSocket
from starlette.websockets import WebSocketDisconnect

logger = logging.getLogger(__name__)

from callio.config.settings import Settings, get_settings
from callio.voice.actions import hermes_tool_definition
from callio.voice.prompt import build_system_prompt
from callio.voice.web_tts import create_web_audio_tts
from callio.voice.whisper_loader import create_whisper_stt, preload_whisper, wait_for_whisper


async def on_user_speech_start(transport, pipeline) -> None:
    if hasattr(transport, "send_control_message"):
        await transport.send_control_message({"action": "mute_tts"})
    if hasattr(pipeline, "clear_buffers"):
        pipeline.clear_buffers()
    if hasattr(pipeline, "cancel_current_task"):
        pipeline.cancel_current_task()


async def execute_hermes_coding(params) -> None:
    summary = params.arguments.get("summary", "")
    actions = params.arguments.get("actions", [])

    hermes_prompt = (
        f"【本地语音脑暴结论】：{summary}\n"
        f"【请立即执行以下 Action 清单】：\n" + "\n".join([f"- {a}" for a in actions]) +
        "\n请自主思考、修改本地文件，并运行测试验证代码正确性。"
    )

    print(f"\n🤖 [Hermes Agent 唤醒] 本地后台开始工作... 任务内容:\n{hermes_prompt}\n")

    try:
        process = await asyncio.create_subprocess_exec(
            "hermes", "run", "--task", hermes_prompt,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        asyncio.create_task(monitor_hermes(process))
        result_msg = "Hermes 已经在您的 Mac 后台启动，正在本地重构代码库..."
    except Exception as e:
        result_msg = f"唤醒 Hermes 失败: {str(e)}"

    await params.result_callback({"status": "triggered", "message": result_msg})


async def monitor_hermes(process: asyncio.subprocess.Process) -> None:
    stdout, stderr = await process.communicate()
    if process.returncode == 0:
        print("\n🎉 [Hermes 结束] 本地自动化编码与测试全部通过！")
    else:
        print(f"\n❌ [Hermes 失败] 本地执行出错: {stderr.decode()}")


def register_voice_routes(app: FastAPI, settings: Settings | None = None) -> None:
    settings = settings or get_settings()

    if not hasattr(app.state, "voice_runners"):
        app.state.voice_runners = set()

    @app.on_event("startup")
    async def preload_whisper_on_startup() -> None:
        await preload_whisper(settings)

    @app.on_event("shutdown")
    async def shutdown_voice_sessions() -> None:
        runners = list(app.state.voice_runners)
        if not runners:
            return
        await asyncio.gather(
            *(runner.cancel(reason="server shutdown") for runner in runners),
            return_exceptions=True,
        )
        app.state.voice_runners.clear()

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        try:
            from pipecat.adapters.schemas.function_schema import FunctionSchema
            from pipecat.adapters.schemas.tools_schema import ToolsSchema
            from pipecat.audio.vad.silero import SileroVADAnalyzer
            from pipecat.audio.vad.vad_analyzer import VADParams
            from pipecat.frames.frames import (
                Frame,
                InputAudioRawFrame,
                InterruptionFrame,
                OutputAudioRawFrame,
                StartFrame,
                TextFrame,
                TranscriptionFrame,
                TTSTextFrame,
            )
            from pipecat.pipeline.pipeline import Pipeline
            from pipecat.pipeline.task import PipelineTask
            from pipecat.workers.runner import WorkerRunner
            from pipecat.processors.aggregators.llm_context import LLMContext
            from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
            from pipecat.processors.audio.vad_processor import VADProcessor
            from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
            from pipecat.serializers.base_serializer import FrameSerializer
            from pipecat.services.ollama.llm import OLLamaLLMService, OllamaLLMSettings
            from pipecat.transcriptions.language import Language
            from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams, FastAPIWebsocketTransport
        except Exception:
            await websocket.accept()
            await websocket.send_json({
                "type": "assistant",
                "text": "语音依赖未安装，状态与任务接口已可用。",
            })
            await websocket.close()
            return

        class RawPCMSerializer(FrameSerializer):
            def __init__(self, sample_rate: int = 16000, num_channels: int = 1, **kwargs):
                super().__init__(**kwargs)
                self._sample_rate = sample_rate
                self._num_channels = num_channels

            async def setup(self, frame: StartFrame):
                if frame.audio_in_sample_rate:
                    self._sample_rate = frame.audio_in_sample_rate

            async def deserialize(self, data: str | bytes) -> Frame | None:
                if isinstance(data, str) or not data:
                    return None
                return InputAudioRawFrame(
                    audio=data,
                    sample_rate=self._sample_rate,
                    num_channels=self._num_channels,
                )

            async def serialize(self, frame: Frame) -> str | bytes | None:
                if isinstance(frame, OutputAudioRawFrame):
                    return frame.audio
                if isinstance(frame, TranscriptionFrame):
                    return json.dumps({"type": "transcription", "text": frame.text})
                if isinstance(frame, TextFrame):
                    return json.dumps({"type": "assistant", "text": frame.text})
                return None

        class WebSocketUIProcessor(FrameProcessor):
            """把转写/回复文本推给浏览器（aggregator 会吞掉 TranscriptionFrame）。"""

            def __init__(self, ws: WebSocket, *, role: str, **kwargs):
                super().__init__(**kwargs)
                self._websocket = ws
                self._role = role

            async def process_frame(self, frame: Frame, direction: FrameDirection):
                await super().process_frame(frame, direction)
                try:
                    if isinstance(frame, InterruptionFrame):
                        await self._websocket.send_text(json.dumps({"type": "interrupt"}))
                    elif self._role == "user" and isinstance(frame, TranscriptionFrame) and frame.text:
                        await self._websocket.send_text(
                            json.dumps({"type": "transcription", "text": frame.text}, ensure_ascii=False)
                        )
                    elif self._role == "assistant" and isinstance(frame, (TextFrame, TTSTextFrame)) and frame.text:
                        await self._websocket.send_text(
                            json.dumps({"type": "assistant", "text": frame.text}, ensure_ascii=False)
                        )
                except Exception as e:
                    logger.warning(f"WebSocket UI push failed: {e}")
                await self.push_frame(frame, direction)

        await websocket.accept()
        await wait_for_whisper(settings)

        transport = FastAPIWebsocketTransport(
            websocket,
            FastAPIWebsocketParams(
                audio_in_enabled=True,
                audio_in_sample_rate=settings.audio_in_sample_rate,
                audio_out_enabled=True,
                audio_out_sample_rate=settings.audio_in_sample_rate,
                serializer=RawPCMSerializer(sample_rate=settings.audio_in_sample_rate),
            ),
        )

        vad = VADProcessor(
            vad_analyzer=SileroVADAnalyzer(
                params=VADParams(start_secs=0.2, stop_secs=0.5, min_volume=0.2)
            )
        )

        stt = create_whisper_stt(settings)

        llm = OLLamaLLMService(
            base_url=settings.ollama_base_url,
            settings=OllamaLLMSettings(model=settings.llm_model),
        )

        tts = create_web_audio_tts(sample_rate=settings.audio_in_sample_rate)

        tool_def = hermes_tool_definition()
        hermes_schema = FunctionSchema(
            name=tool_def["name"],
            description=tool_def["description"],
            properties=tool_def["properties"],
            required=tool_def["required"],
        )
        llm.register_function("execute_hermes_coding", execute_hermes_coding, cancel_on_interruption=False)

        context = LLMContext(
            messages=[{"role": "system", "content": build_system_prompt(settings.voice_response_limit)}],
            tools=ToolsSchema(standard_tools=[hermes_schema]),
        )
        context_aggregator = LLMContextAggregatorPair(context)

        pipeline = Pipeline([
            transport.input(),
            vad,
            stt,
            WebSocketUIProcessor(websocket, role="user"),
            context_aggregator.user(),
            llm,
            WebSocketUIProcessor(websocket, role="assistant"),
            tts,
            transport.output(),
            context_aggregator.assistant(),
        ])

        task = PipelineTask(pipeline)
        runner = WorkerRunner(handle_sigint=False, handle_sigterm=False)
        app.state.voice_runners.add(runner)

        @transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(_transport, _client_ws) -> None:
            await runner.cancel(reason="client disconnected")

        print("\n⚡ 本地全双工语音管道已握手成功，开始处理音频流...")
        try:
            await runner.run(task)
        except WebSocketDisconnect:
            logger.info("Voice WebSocket disconnected")
        finally:
            app.state.voice_runners.discard(runner)
            await runner.cancel(reason="session ended")

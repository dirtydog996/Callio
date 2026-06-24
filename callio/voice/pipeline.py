from __future__ import annotations

import asyncio
import json
import logging

from fastapi import FastAPI, WebSocket
from starlette.websockets import WebSocketDisconnect

logger = logging.getLogger(__name__)

from callio.config.settings import Settings, get_settings
from callio.voice.memory_context import build_memory_block
from callio.voice.prompt import build_system_prompt
from callio.voice.resume_context import build_resume_block
from callio.voice.tools.handlers import create_tool_handlers
from callio.voice.tools.schemas import all_tool_definitions
from callio.voice.session_hook import SessionHook
from callio.voice.notifier import notify_session_finished
from callio.voice.tts_loader import preload_tts, wait_for_tts
from callio.voice.web_tts import create_tts
from callio.voice.whisper_loader import create_whisper_stt, preload_whisper, wait_for_whisper


def _create_stt(settings: Settings):
    """Return the appropriate STT service based on *stt_backend* setting."""
    backend = (settings.stt_backend or "whisper").strip().lower()
    if backend == "sensevoice":
        from callio.voice.funasr_loader import create_sensevoice_stt
        return create_sensevoice_stt(settings)
    return create_whisper_stt(settings)


async def on_user_speech_start(transport, pipeline) -> None:
    if hasattr(transport, "send_control_message"):
        await transport.send_control_message({"action": "mute_tts"})
    if hasattr(pipeline, "clear_buffers"):
        pipeline.clear_buffers()
    if hasattr(pipeline, "cancel_current_task"):
        pipeline.cancel_current_task()


def register_voice_routes(app: FastAPI, settings: Settings | None = None) -> None:
    settings = settings or get_settings()

    if not hasattr(app.state, "voice_runners"):
        app.state.voice_runners = set()

    @app.on_event("startup")
    async def preload_voice_models_on_startup() -> None:
        backend = (settings.stt_backend or "whisper").strip().lower()
        if backend == "sensevoice":
            from callio.voice.funasr_loader import preload_funasr
            await asyncio.gather(preload_funasr(settings), preload_tts(settings))
        else:
            await asyncio.gather(preload_whisper(settings), preload_tts(settings))

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
        orchestrator = getattr(app.state, "orchestrator", None)
        memory_hub = getattr(app.state, "memory_hub", None)
        connection_id = id(websocket)
        session_id: str | None = None
        session_ctx = None
        resume_block = ""
        history_messages: list[dict[str, str]] = []

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
                VADUserStartedSpeakingFrame,
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
            from callio.llm.voice_factory import build_voice_llm_service
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

        class BargeInProcessor(FrameProcessor):
            async def process_frame(self, frame: Frame, direction: FrameDirection):
                await super().process_frame(frame, direction)
                if isinstance(frame, VADUserStartedSpeakingFrame):
                    await self.broadcast_frame(InterruptionFrame)
                await self.push_frame(frame, direction)

        class WebSocketUIProcessor(FrameProcessor):
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
        backend = (settings.stt_backend or "whisper").strip().lower()
        if backend == "sensevoice":
            from callio.voice.funasr_loader import wait_for_funasr
            await wait_for_funasr(settings)
        else:
            await wait_for_whisper(settings)
        await wait_for_tts(settings)

        if orchestrator is not None:
            resume_session_id = websocket.query_params.get("resume_session_id")
            session_ctx = orchestrator.sessions.open(
                connection_id,
                resume_session_id=resume_session_id or None,
            )
            session_id = session_ctx.session_id
            resume_block = ""
            history_messages: list[dict[str, str]] = []
            if session_ctx.resumed:
                from callio.voice.resume_context import parse_transcript_messages

                session_row = orchestrator.database.get_session(session_id) or {}
                transcript = str(session_row.get("transcript", ""))
                if transcript:
                    orchestrator.transcripts.hydrate(session_id, transcript)
                    history_messages = parse_transcript_messages(transcript)
                resume_block = build_resume_block(orchestrator.database, session_id)
            await websocket.send_json({
                "type": "session",
                "session_id": session_id,
                "resumed": session_ctx.resumed,
                "title": session_ctx.title,
            })
            await orchestrator.event_bus.emit(
                session_id,
                "SESSION_RESUMED" if session_ctx.resumed else "SESSION_STARTED",
                {"title": session_ctx.title, "resumed": session_ctx.resumed},
            )

        transport = FastAPIWebsocketTransport(
            websocket,
            FastAPIWebsocketParams(
                audio_in_enabled=True,
                audio_in_sample_rate=settings.audio_in_sample_rate,
                audio_out_enabled=True,
                audio_out_sample_rate=settings.audio_out_sample_rate,
                serializer=RawPCMSerializer(sample_rate=settings.audio_in_sample_rate),
            ),
        )

        vad = VADProcessor(
            vad_analyzer=SileroVADAnalyzer(
                params=VADParams(start_secs=0.2, stop_secs=0.5, min_volume=0.2)
            )
        )

        stt = _create_stt(settings)

        llm = build_voice_llm_service(settings)

        tts = create_tts(settings)

        progress_block = ""
        memory_block = ""
        if orchestrator is not None and session_id:
            progress_block = orchestrator.progress.build_context_block(session_id)
        if settings.memory_inject and memory_hub is not None:
            database = getattr(app.state, "database", None)
            if database is not None:
                memory_block = build_memory_block(memory_hub, database)
                if not resume_block and session_id:
                    resume_block = build_resume_block(database, session_id)

        tool_schemas = [
            FunctionSchema(
                name=tool["name"],
                description=tool["description"],
                properties=tool["properties"],
                required=tool["required"],
            )
            for tool in all_tool_definitions()
        ]

        if orchestrator is not None and session_id:
            handlers = create_tool_handlers(orchestrator, session_id)
            for name, handler in handlers.items():
                llm.register_function(name, handler, cancel_on_interruption=False)

        context = LLMContext(
            messages=[{
                "role": "system",
                "content": build_system_prompt(
                    settings.voice_response_limit,
                    progress_block=progress_block,
                    memory_block=memory_block,
                    resume_block=resume_block,
                ),
            }, *history_messages],
            tools=ToolsSchema(standard_tools=tool_schemas) if orchestrator else None,
        )
        context_aggregator = LLMContextAggregatorPair(context)

        processors = [
            transport.input(),
            vad,
            BargeInProcessor(),
            stt,
            WebSocketUIProcessor(websocket, role="user"),
        ]
        if orchestrator is not None and session_id:
            processors.append(
                SessionHook(orchestrator, session_id, context, settings, memory_hub=memory_hub)
            )
        processors.extend([
            context_aggregator.user(),
            llm,
            WebSocketUIProcessor(websocket, role="assistant"),
            tts,
            transport.output(),
            context_aggregator.assistant(),
        ])

        pipeline = Pipeline(processors)

        task = PipelineTask(pipeline)
        runner = WorkerRunner(handle_sigint=False, handle_sigterm=False)
        app.state.voice_runners.add(runner)

        @transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(_transport, _client_ws) -> None:
            await runner.cancel(reason="client disconnected")

        print("\n⚡ 本地全双工语音管道已握手成功，开始处理音频流...")
        if session_id:
            resumed_label = "（续聊）" if session_ctx and session_ctx.resumed else ""
            print(f"📋 会话 ID: {session_id}{resumed_label}")
        try:
            await runner.run(task)
        except WebSocketDisconnect:
            logger.info("Voice WebSocket disconnected")
        finally:
            app.state.voice_runners.discard(runner)
            await runner.cancel(reason="session ended")
            if orchestrator is not None and session_id:
                transcript = await orchestrator.transcripts.flush(session_id)
                await orchestrator.coordinator.finalize_summary(session_id, transcript)
                await orchestrator.sessions.finalize(connection_id, transcript=transcript)
                session_row = orchestrator.database.get_session(session_id) or {}
                notify_session_finished(
                    settings,
                    session_id=session_id,
                    session_title=str(session_row.get("title", session_ctx.title if session_ctx else "")),
                    transcript=transcript,
                    summary=str(session_row.get("summary", "")),
                )

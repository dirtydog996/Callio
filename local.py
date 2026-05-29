import asyncio
import os
import subprocess
import sys
import pyttsx3
from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
import uvicorn
from dotenv import load_dotenv
from typing import AsyncGenerator

# Pipecat 核心组件
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair

# ===== 纯本地组件导入 =====
from pipecat.transports.websocket.fastapi import FastAPIWebsocketTransport, FastAPIWebsocketParams
from pipecat.services.whisper.stt import WhisperSTTService
from pipecat.services.ollama.llm import OLLamaLLMService
from pipecat.services.tts_service import TTSService
from pipecat.frames.frames import Frame, TTSAudioRawFrame, TTSStartedFrame, TTSStoppedFrame

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.services.llm_service import FunctionCallParams

load_dotenv()
app = FastAPI()

# 挂载静态目录，方便手机端访问 HTML 页面
if not os.path.exists("static"):
    os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")

# ========================================================
# 自定义封装：Mac 本地原生离线引擎 (pyttsx3)
# ========================================================
class MacNativeTTSService(TTSService):
    def __init__(self):
        super().__init__(push_stop_frames=True, sample_rate=22050)
        # 初始化 Mac 系统级语音引擎
        try:
            self.engine = pyttsx3.init(driverName='nsss')
        except:
            self.engine = pyttsx3.init()
        voices = self.engine.getProperty('voices')
        # 寻找普通的中文普通话女声/男声
        for voice in voices:
            if "zh" in voice.languages or "CN" in voice.id:
                self.engine.setProperty('voice', voice.id)
                break
        self.engine.setProperty('rate', 175) # 语速调整

    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame | None, None]:
        """将大模型吐出的文字通过系统原生转成音频流"""
        print(f"🎙️ [本地 TTS 发声]: {text}")

        # pyttsx3 本身是阻塞的，用 asyncio 丢进线程池防止卡死全双工流水线
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._speak, text)

        # pyttsx3 无法直接提供音频帧给 pipeline，音频直接通过系统扬声器播放
        yield None

    def _speak(self, text):
        self.engine.say(text)
        self.engine.runAndWait()


# ========================================================
# 1. 后台 Hermes Coding 异步任务（保持不变）
# ========================================================
async def execute_hermes_coding(params: FunctionCallParams):
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
            stderr=subprocess.PIPE
        )
        asyncio.create_task(monitor_hermes(process))
        result_msg = "Hermes 已经在您的 Mac 后台启动，正在本地重构代码库..."
    except Exception as e:
        result_msg = f"唤醒 Hermes 失败: {str(e)}"

    await params.result_callback({"status": "triggered", "message": result_msg})

async def monitor_hermes(process):
    stdout, stderr = await process.communicate()
    if process.returncode == 0:
        print("\n🎉 [Hermes 结束] 本地自动化编码与测试全部通过！")
    else:
        print(f"\n❌ [Hermes 失败] 本地执行出错: {stderr.decode()}")


# ========================================================
# 2. 纯本地语音流水线路由
# ========================================================
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    transport = FastAPIWebsocketTransport(
        websocket,
        FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True
        )
    )

    # 1. 本地耳朵：Faster-Whisper (首次运行自动下载 base 尺寸模型，仅几百M，后续断网可用)
    stt = WhisperSTTService(model="base", device="cpu")

    # 2. 本地大脑：直连本地 Ollama (确保运行着 qwen2.5-coder)
    llm = OLLamaLLMService(
        base_url="http://localhost:11434/v1",
        model="qwen2.5-coder:7b"
    )

    # 3. 本地嘴巴：调用刚刚封装好的 Mac 系统原生离线 TTS
    tts = MacNativeTTSService() 

    hermes_schema = FunctionSchema(
        name="execute_hermes_coding",
        description="当用户说‘开始落实’时触发，调用后台 Hermes 执行具体的代码重构。",
        properties={
            "summary": {"type": "string", "description": "头脑风暴得出的功能和架构结论"},
            "actions": {"type": "array", "items": {"type": "string"}, "description": "需要修改的文件清单"}
        },
        required=["summary", "actions"]
    )
    llm.register_function("execute_hermes_coding", execute_hermes_coding, cancel_on_interruption=False)

    sys_message = {
        "role": "system",
        "content": "你是一个运行在本地的语音助手。负责陪同用户脑暴架构。保持每句话在 30 字以内。确认落实后立刻触发工具。"
    }
    
    tools = ToolsSchema(standard_tools=[hermes_schema])
    context = LLMContext(messages=[sys_message], tools=tools)
    context_aggregator = LLMContextAggregatorPair(context)

    pipeline = Pipeline([
        transport.input(),
        stt,
        context_aggregator.user(),
        llm,
        tts,
        transport.output(),
        context_aggregator.assistant()
    ])

    task = PipelineTask(pipeline)
    runner = PipelineRunner()
    
    print("\n⚡ 本地全双工语音管道已握手成功，开始处理音频流...")
    await runner.run(task)


# ========================================================
# 3. 自动计算局域网 IP 并弹窗展示迷你二维码
# ========================================================
def show_local_qr():
    import socket
    import tempfile
    import qrcode
    
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        local_ip = s.getsockname()[0]
    except Exception:
        local_ip = '127.0.0.1'
    finally:
        s.close()
        
    local_url = f"http://{local_ip}:8000/static/index.html"
    print(f"\n=======================================================")
    print(f"🏠 纯本地全双工服务已启动！")
    print(f"🔗 局域网 Web 调试端链接: {local_url}")
    print(f"=======================================================")
    
    qr = qrcode.QRCode(version=1, box_size=5, border=1)
    qr.add_data(local_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
        img.save(tmp.name)
        subprocess.run(["open", tmp.name])

if __name__ == "__main__":
    if len(sys.argv) == 1 or sys.argv[1] != "worker":
        show_local_qr()
    uvicorn.run("local:app", host="0.0.0.0", port=8000, reload=False)

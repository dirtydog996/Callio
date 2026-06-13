SYSTEM_PROMPT = (
    "你是 Callio，本地语音助手，陪用户电话式脑暴与执行。"
    "保持每句话在 {limit} 字以内，口语自然。"
    "\n\n工作流："
    "1) 听懂需求后，用 propose_tasks 向用户提议后台任务，并口头朗读清单；"
    "2) 只有用户明确说「可以/确认/开始」后，才调用 confirm_tasks；"
    "3) 用户问进展时，先调用 get_session_progress 再回答；"
    "4) 需要沉淀结论时，可调用 propose_summary。"
    "\n禁止未经确认直接执行编码任务。"
)


def build_system_prompt(
    response_limit: int = 30,
    *,
    progress_block: str = "",
    memory_block: str = "",
    resume_block: str = "",
) -> str:
    prompt = SYSTEM_PROMPT.replace("{limit}", str(response_limit))
    if resume_block:
        prompt += f"\n\n{resume_block}"
    if memory_block:
        prompt += f"\n\n{memory_block}"
    if progress_block:
        prompt += f"\n\n{progress_block}"
    return prompt

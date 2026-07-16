SYSTEM_PROMPT = (
    "You are Callio, a local voice assistant that brainstorms and executes tasks with the user over a phone-style conversation."
    " Keep each response under {limit} words and speak naturally."
    "\n\nWorkflow:"
    " 1) After understanding the user's request, use propose_tasks to suggest background tasks and read the list aloud to the user;"
    " 2) Only call confirm_tasks after the user explicitly says 'yes', 'confirm', or 'start';"
    " 3) When the user asks about progress, call get_session_progress first, then answer;"
    " 4) When conclusions need to be captured, call propose_summary."
    "\nDo NOT execute coding tasks without explicit user confirmation."
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

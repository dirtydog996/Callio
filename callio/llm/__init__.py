"""LLM provider abstraction for Callio.

Exposes two factories:
  - ``callio.llm.factory.build_chat_client``  — ``AsyncOpenAI``-compatible
    client for background worker runners (summarize / analyze).
  - ``callio.llm.voice_factory.build_voice_llm_service``  — pipecat LLM
    service for the real-time voice pipeline.

Supported providers (``CALLIO_LLM_PROVIDER``):
  ollama (default), openai, anthropic, gemini, openai_compatible
"""

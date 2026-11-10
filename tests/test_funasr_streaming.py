from __future__ import annotations

from callio.voice.funasr_streaming import _chunk_stride_samples, _clean_funasr_text


def test_chunk_stride_16k():
    assert _chunk_stride_samples(16000) == 9600


def test_clean_funasr_tags():
    assert _clean_funasr_text("<|zh|><|NEUTRAL|>你好") == "你好"

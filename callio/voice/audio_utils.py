from __future__ import annotations

import io
import wave

import numpy as np

_CHUNK_MS = 20


def resample_float32(samples: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    if len(samples) == 0 or source_rate == target_rate:
        return samples

    ratio = source_rate / target_rate
    out_len = max(1, int(len(samples) / ratio))
    src_indices = np.arange(len(samples), dtype=np.float64)
    dst_indices = np.arange(out_len, dtype=np.float64) * ratio
    return np.interp(dst_indices, src_indices, samples).astype(np.float32)


def float32_to_pcm_bytes(samples: np.ndarray, *, source_rate: int, target_rate: int) -> bytes:
    if len(samples) == 0:
        return b""

    mono = samples.astype(np.float32, copy=False)
    if mono.ndim > 1:
        mono = mono.reshape(-1, mono.shape[-1]).mean(axis=1)

    mono = resample_float32(mono, source_rate, target_rate)
    return (np.clip(mono, -1.0, 1.0) * 32767).astype(np.int16).tobytes()


def wav_to_pcm_bytes(wav_bytes: bytes, target_rate: int) -> bytes:
    with io.BytesIO(wav_bytes) as buffer:
        with wave.open(buffer, "rb") as wf:
            channels = wf.getnchannels()
            source_rate = wf.getframerate()
            pcm = wf.readframes(wf.getnframes())

    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return float32_to_pcm_bytes(samples, source_rate=source_rate, target_rate=target_rate)


def iter_pcm_chunks(pcm: bytes, sample_rate: int, *, chunk_ms: int = _CHUNK_MS) -> list[bytes]:
    bytes_per_chunk = int(sample_rate * (chunk_ms / 1000.0) * 2)
    bytes_per_chunk = max(bytes_per_chunk, 2)
    return [
        pcm[i : i + bytes_per_chunk]
        for i in range(0, len(pcm), bytes_per_chunk)
        if pcm[i : i + bytes_per_chunk]
    ]

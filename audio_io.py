import asyncio
import logging
import threading
from typing import AsyncGenerator

# Import sounddevice only when needed
try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    sd = None
    SOUNDDEVICE_AVAILABLE = False

from audio_utils import rms_energy

SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH_BYTES = 2  # int16
FRAME_MS = 20
FRAME_SAMPLES = int(SAMPLE_RATE * FRAME_MS / 1000)
FRAME_BYTES = FRAME_SAMPLES * SAMPLE_WIDTH_BYTES * CHANNELS

logger = logging.getLogger(__name__)

_output_stream = None
_output_stream_lock = threading.Lock()


def _ensure_output_stream():
    if not SOUNDDEVICE_AVAILABLE:
        raise RuntimeError("sounddevice not available in this environment")
    
    global _output_stream
    if _output_stream is None:
        _output_stream = sd.RawOutputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=0,
            latency="low",
        )
        _output_stream.start()
    return _output_stream


async def _write_audio(pcm_bytes: bytes) -> None:
    if not SOUNDDEVICE_AVAILABLE:
        raise RuntimeError("sounddevice not available in this environment")
    
    stream = _ensure_output_stream()
    with _output_stream_lock:
        stream.write(pcm_bytes)


async def play_audio(pcm_bytes: bytes) -> None:
    if not SOUNDDEVICE_AVAILABLE:
        # In web environments, audio is handled differently
        return
        
    if not pcm_bytes:
        return
    await asyncio.to_thread(_write_audio, pcm_bytes)


async def mic_stream() -> AsyncGenerator[bytes, None]:
    if not SOUNDDEVICE_AVAILABLE:
        raise RuntimeError("sounddevice not available in this environment")
        
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=50)

    def callback(indata, frames, time_info, status):
        if status:
            logger.warning("Mic stream status: %s", status)
        try:
            queue.put_nowait(bytes(indata))
        except asyncio.QueueFull:
            # Drop oldest to keep latency low
            try:
                _ = queue.get_nowait()
                queue.put_nowait(bytes(indata))
            except asyncio.QueueEmpty:
                pass

    stream = sd.RawInputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="int16",
        blocksize=FRAME_SAMPLES,
        latency="low",
        callback=callback,
    )

    with stream:
        while True:
            chunk = await queue.get()
            if len(chunk) != FRAME_BYTES:
                # Pad or trim to fixed 20ms frames
                if len(chunk) < FRAME_BYTES:
                    chunk = chunk + b"\x00" * (FRAME_BYTES - len(chunk))
                else:
                    chunk = chunk[:FRAME_BYTES]
            yield chunk


# rms_energy is provided by audio_utils to avoid sounddevice dependency in web server paths.

import asyncio
import sys

from call_session import CallSession
from config import get_env, get_env_bool, load_dotenv
from logging_utils import configure_logging, mask_secret
from sarvam_llm_service import SarvamLLMService
from sarvam_stt_service import SaarikaSTTService


async def _run() -> None:
    load_dotenv(override=True)
    stt_ws_url = get_env(
        "SAARIKA_WS_URL",
        get_env("SARVAM_STT_WS_URL", "wss://api.sarvam.ai/speech-to-text/ws"),
    )
    llm_base_url = get_env("SARVAM_BASE_URL", "https://api.sarvam.ai")
    tts_ws_url = get_env(
        "BULBUL_WS_URL",
        get_env("SARVAM_TTS_WS_URL", "wss://api.sarvam.ai/text-to-speech/ws"),
    )

    api_key = get_env("SARVAM_API_KEY")
    stt_api_key = get_env("SAARIKA_API_KEY", api_key)
    llm_api_key = get_env("SARVAM_LLM_API_KEY", api_key)
    tts_api_key = get_env("BULBUL_API_KEY", api_key)
    if not stt_api_key:
        raise RuntimeError("Missing SAARIKA_API_KEY for STT.")

    llm_model = get_env("SARVAM_CHAT_MODEL", get_env("SARVAM_LLM_MODEL", "sarvam-m"))
    tts_speaker = get_env("SARVAM_TTS_SPEAKER", "shubh")
    tts_voice = get_env("BULBUL_VOICE")
    stt_model = get_env("SARVAM_STT_MODEL")
    tts_model = get_env("SARVAM_TTS_MODEL", "bulbul:v3")
    stt_language = get_env("SARVAM_STT_LANGUAGE", "en-IN")
    stt_language_key = get_env("SARVAM_STT_LANGUAGE_PARAM", "language_code")

    vad_threshold = float(get_env("VAD_RMS_THRESHOLD", "500"))
    vad_silence_ms = int(get_env("VAD_SILENCE_MS", "600"))
    stt_flush_interval_ms = int(get_env("STT_FLUSH_INTERVAL_MS", "250"))
    stt_vad_signals = get_env_bool("STT_VAD_SIGNALS", True)
    stt_high_vad = get_env_bool("STT_HIGH_VAD_SENSITIVITY", True)
    stt_flush_signal_env = get_env("STT_FLUSH_SIGNAL")
    use_sdk = get_env_bool("USE_SARVAMAI_SDK", True)
    use_sdk_stt = get_env_bool("USE_SARVAMAI_SDK_STT", use_sdk)

    if stt_flush_signal_env is None or stt_flush_signal_env == "":
        stt_flush_signal = use_sdk_stt
    else:
        stt_flush_signal = get_env_bool("STT_FLUSH_SIGNAL", False)

    stt_audio_payload_format = get_env("STT_AUDIO_PAYLOAD_FORMAT", "flat")
    stt_input_audio_codec = get_env("STT_INPUT_AUDIO_CODEC", "pcm_s16le")
    stt_audio_encoding = get_env("STT_AUDIO_ENCODING")
    stt_log_raw = get_env_bool("LOG_STT_RAW", False)

    # SDK TTS streams MP3; speaker expects PCM16. Default to raw WS unless explicitly enabled.
    use_sdk_tts = get_env_bool("USE_SARVAMAI_SDK_TTS", False)
    # LLM streaming via SDK doesn't handle event-stream correctly; default to HTTP SSE unless overridden.
    use_sdk_llm = get_env_bool("USE_SARVAMAI_SDK_LLM", False)

    greeting_text = get_env(
        "GREETING_TEXT",
        "Hello! This is Anushka from TuringEdge collections, calling about your overdue payment. Is now a good time to talk?",
    )
    enable_greeting = get_env_bool("ENABLE_GREETING", True)
    max_history_turns = int(get_env("MAX_HISTORY_TURNS", "10"))
    session_store_path = get_env("SESSION_STORE_PATH")
    dynamic_stt_language = get_env_bool("STT_DYNAMIC_LANGUAGE", True)
    preview_partials = get_env_bool("PREVIEW_PARTIALS", True)
    preview_after_ms = int(get_env("PREVIEW_AFTER_MS", "300"))
    llm_timeout_s = float(get_env("LLM_STREAM_TIMEOUT_S", "20"))
    tts_timeout_s = float(get_env("TTS_STREAM_TIMEOUT_S", "20"))
    stt_connect_timeout_s = float(get_env("STT_CONNECT_TIMEOUT_S", "10"))
    tts_stream_chunk_chars = int(get_env("TTS_STREAM_CHUNK_CHARS", "30"))
    tts_stream_flush_punct = get_env_bool("TTS_STREAM_FLUSH_PUNCT", True)
    tts_min_buffer_size = int(get_env("TTS_MIN_BUFFER_SIZE", "30"))
    tts_max_chunk_length = int(get_env("TTS_MAX_CHUNK_LENGTH", "120"))
    tts_output_audio_codec = get_env("TTS_OUTPUT_AUDIO_CODEC", "linear16")
    tts_output_audio_bitrate = get_env("TTS_OUTPUT_AUDIO_BITRATE")

    stt = SaarikaSTTService(
        ws_url=stt_ws_url,
        api_key=stt_api_key,
        model=stt_model,
        language=stt_language,
        language_param_key=stt_language_key,
        vad_signals=stt_vad_signals,
        high_vad_sensitivity=stt_high_vad,
        flush_signal=stt_flush_signal,
        audio_payload_format=stt_audio_payload_format,
        input_audio_codec=stt_input_audio_codec,
        audio_encoding=stt_audio_encoding,
        log_raw_messages=stt_log_raw,
        use_sdk=use_sdk_stt,
    )
    llm = SarvamLLMService(
        base_url=llm_base_url,
        api_key=llm_api_key,
        model=llm_model,
        use_sdk=use_sdk_llm,
    )

    session = CallSession(
        stt_service=stt,
        llm_service=llm,
        tts_ws_url=tts_ws_url,
        tts_api_key=tts_api_key,
        tts_voice=tts_voice,
        tts_model=tts_model,
        tts_speaker=tts_speaker,
        greeting_text=greeting_text if enable_greeting else None,
        max_history_turns=max_history_turns,
        session_store_path=session_store_path,
        dynamic_stt_language=dynamic_stt_language,
        preview_partials=preview_partials,
        preview_after_ms=preview_after_ms,
        llm_timeout_s=llm_timeout_s,
        tts_timeout_s=tts_timeout_s,
        stt_connect_timeout_s=stt_connect_timeout_s,
        vad_rms_threshold=vad_threshold,
        vad_silence_ms=vad_silence_ms,
        stt_flush_interval_ms=stt_flush_interval_ms,
        use_sdk=use_sdk_tts,
        tts_stream_chunk_chars=tts_stream_chunk_chars,
        tts_stream_flush_punct=tts_stream_flush_punct,
        tts_min_buffer_size=tts_min_buffer_size,
        tts_max_chunk_length=tts_max_chunk_length,
        tts_output_audio_codec=tts_output_audio_codec,
        tts_output_audio_bitrate=tts_output_audio_bitrate,
    )

    await session.run()


def main() -> None:
    load_dotenv(override=True)
    configure_logging()
    # CHANGE: Only log masked keys when explicitly requested.
    if get_env_bool("DEBUG_CONFIG", False):
        import logging

        logging.getLogger(__name__).info(
            "config_loaded api_key=%s", mask_secret(get_env("SARVAM_API_KEY"))
        )
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        print("\nSession stopped by user.")
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

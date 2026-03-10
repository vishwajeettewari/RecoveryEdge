from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config import get_env, get_env_bool, load_dotenv
from sarvam_tts_service import BulbulTTSService


MANIFEST_PATH = ROOT / "scenarios.json"
OUTPUT_DIR = ROOT / "generated"
SCRIPT_DIR = OUTPUT_DIR / "scripts"
TEMP_DIR = OUTPUT_DIR / "_tmp"


def ensure_tool(name: str) -> None:
    if shutil.which(name):
        return
    raise RuntimeError(f"Required tool not found on PATH: {name}")


def load_manifest() -> list[dict]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def write_script_file(scenario: dict) -> Path:
    SCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    script_path = SCRIPT_DIR / f"{scenario['id']}.txt"
    script_path.write_text(str(scenario["script"]).strip() + "\n", encoding="utf-8")
    return script_path


def synthesize_aiff(*, voice: str, rate: int, script_path: Path, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["say", "-v", voice, "-r", str(rate), "-o", str(output_path), "--input-file", str(script_path)],
        check=True,
    )
    if output_path.stat().st_size <= 4096:
        raise RuntimeError(f"say generated an empty audio file for {output_path.name}")


async def _collect_audio(tts: BulbulTTSService) -> bytes:
    chunks: list[bytes] = []
    async for chunk in tts.audio_stream():
        chunks.append(chunk)
    return b"".join(chunks)


def synthesize_wav_with_sarvam(*, scenario: dict, output_path: Path) -> None:
    load_dotenv(override=False)
    api_key = get_env("BULBUL_API_KEY", get_env("SARVAM_API_KEY"))
    if not api_key:
        raise RuntimeError("No BULBUL_API_KEY or SARVAM_API_KEY found in the environment or .env")
    ws_url = get_env("SARVAM_TTS_WS_URL", "wss://api.sarvam.ai/text-to-speech/ws")
    model = get_env("SARVAM_TTS_MODEL", "bulbul:v3")
    use_sdk = get_env_bool("USE_SARVAMAI_SDK_TTS", False)
    speaker = str(scenario.get("speaker") or "shubh").strip().lower() or "shubh"
    language = str(scenario.get("language") or "en-IN").strip() or "en-IN"
    text = str(scenario["script"]).strip()
    timeout_s = float(get_env("AUDIO_PACK_TTS_TIMEOUT_S", "45") or 45)

    async def _run() -> bytes:
        async with BulbulTTSService(
            ws_url=ws_url,
            api_key=api_key,
            model=model,
            speaker=speaker,
            sample_rate=16000,
            language=language,
            output_audio_codec="linear16",
            use_sdk=use_sdk,
        ) as tts:
            collect_task = asyncio.create_task(_collect_audio(tts))
            await tts.send_text(text)
            await tts.end_input()
            return await collect_task

    try:
        audio_bytes = asyncio.run(asyncio.wait_for(_run(), timeout=timeout_s))
    except TimeoutError as exc:
        raise RuntimeError(
            f"Sarvam TTS timed out after {timeout_s:.0f}s while generating {scenario['id']}"
        ) from exc
    if not audio_bytes:
        raise RuntimeError(f"Sarvam TTS returned no audio for {scenario['id']}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(audio_bytes)


def convert_with_effect(*, effect: str, input_path: Path, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    base_cmd = ["ffmpeg", "-y", "-i", str(input_path)]
    if effect == "clean":
        cmd = base_cmd + ["-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(output_path)]
    elif effect == "telephone_noise":
        cmd = base_cmd + [
            "-f",
            "lavfi",
            "-i",
            "anoisesrc=color=white:amplitude=0.015",
            "-filter_complex",
            "[0:a]highpass=f=250,lowpass=f=3400,volume=1.05[voice];"
            "[1:a]volume=0.09[noise];"
            "[voice][noise]amix=inputs=2:duration=first:normalize=0",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
    elif effect == "low_volume":
        cmd = base_cmd + [
            "-af",
            "volume=0.23",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
    else:
        raise RuntimeError(f"Unsupported effect: {effect}")
    subprocess.run(cmd, check=True)


def write_pack_index(scenarios: list[dict]) -> None:
    lines = [
        "# Collections Audio Pack",
        "",
        "| ID | Category | Voice | Effect | File |",
        "| --- | --- | --- | --- | --- |",
    ]
    for scenario in scenarios:
        wav_name = f"{scenario['id']}.wav"
        lines.append(
            f"| `{scenario['id']}` | {scenario['category']} | {scenario['voice']} | {scenario['effect']} | `generated/{wav_name}` |"
        )
    lines.append("")
    lines.append("Each matching text script is available under `generated/scripts/`.")
    (OUTPUT_DIR / "PACK_INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ensure_tool("ffmpeg")
    load_dotenv(override=False)
    engine = (get_env("AUDIO_PACK_ENGINE", "sarvam") or "sarvam").strip().lower()
    if engine == "say":
        ensure_tool("say")
    scenarios = load_manifest()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    for scenario in scenarios:
        scenario_id = str(scenario["id"])
        script_path = write_script_file(scenario)
        wav_path = OUTPUT_DIR / f"{scenario_id}.wav"
        effect = str(scenario.get("effect") or "clean")
        if engine == "sarvam":
            clean_wav = TEMP_DIR / f"{scenario_id}.clean.wav"
            synthesize_wav_with_sarvam(scenario=scenario, output_path=clean_wav)
            if effect == "clean":
                shutil.copyfile(clean_wav, wav_path)
            else:
                convert_with_effect(effect=effect, input_path=clean_wav, output_path=wav_path)
        elif engine == "say":
            aiff_path = TEMP_DIR / f"{scenario_id}.aiff"
            synthesize_aiff(
                voice=str(scenario["voice"]),
                rate=int(scenario.get("rate", 170)),
                script_path=script_path,
                output_path=aiff_path,
            )
            convert_with_effect(effect=effect, input_path=aiff_path, output_path=wav_path)
        else:
            raise RuntimeError(f"Unsupported AUDIO_PACK_ENGINE: {engine}")
    write_pack_index(scenarios)


if __name__ == "__main__":
    main()

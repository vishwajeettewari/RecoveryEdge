# Collections Voice Test Pack

This pack creates reusable borrower-side audio clips for exercising the calling agent against realistic collections scenarios, not just ideal clean replies.

## What is included

- `scenarios.json`: the scenario manifest with script text, voice choice, effect, and expected behavior.
- `generate_audio_pack.py`: local generator that uses Sarvam TTS by default and can fall back to macOS `say`, with `ffmpeg` for telephony-style effects.
- `generated/*.wav`: the rendered borrower audio files.
- `generated/scripts/*.txt`: one script file per audio clip.
- `generated/PACK_INDEX.md`: a compact file inventory after generation.

## Scenario coverage

- Consent accepted
- Consent refused
- Identity confirmation
- Fragmented mixed-language identity reply
- Already-paid with UTR
- PTP capture
- Callback capture
- Hardship / partial-payment response
- Language-switch request
- Wrong-party denial
- Abusive safe-exit case
- Noisy callback-time extraction
- Low-volume elderly PTP edge case

## Suggested playback bundles

### Happy path

1. `01_consent_clear_yes`
2. `03_identity_clear_name`
3. `06_ptp_specific_date`

Expected outcome: the agent captures consent, confirms identity, records a PTP, and closes politely.

### Paid flow

1. `01_consent_clear_yes`
2. `03_identity_clear_name`
3. `05_already_paid_with_utr`

Expected outcome: the agent captures already-paid status and UTR instead of asking for a new payment promise.

### Callback flow

1. `01_consent_clear_yes`
2. `03_identity_clear_name`
3. `07_callback_specific_time`

Expected outcome: the agent stores a callback and confirms the time cleanly.

### Hardship flow

1. `01_consent_clear_yes`
2. `03_identity_clear_name`
3. `08_hardship_partial_payment`

Expected outcome: the agent stays empathetic, does not threaten, and works toward a realistic resolution.

### Guardrail / edge-case bundle

Use individually as interruption or failure-mode checks:

- `02_consent_refusal`
- `04_identity_fragmented_name_hinglish`
- `09_language_switch_request`
- `10_wrong_party_refusal`
- `11_abusive_safe_exit`
- `12_noisy_callback_low_clarity`
- `13_low_volume_ptp_edge`

## Regeneration

Run:

```bash
python3 testing/audio_pack/generate_audio_pack.py
```

Notes:

- Default engine: Sarvam TTS (`AUDIO_PACK_ENGINE=sarvam`)
- Local fallback: `AUDIO_PACK_ENGINE=say`
- Stream timeout override: `AUDIO_PACK_TTS_TIMEOUT_S=45`
- The generated WAV files are mono, `16 kHz`, and `pcm_s16le`, which makes them convenient for telephony-style STT testing.

# Fix: System Interrupting User During Natural Speech Pauses

## Problem
The system was responding too quickly when users took natural pauses while speaking, causing interruptions and "ruckus". The system would detect silence and immediately start responding, cutting off users mid-sentence.

## Root Cause
1. **Too short pause duration**: Default `post_speech_pause_ms` was only 250ms, which is way too short for natural speech pauses
2. **No cancellation mechanism**: Once the pause timer started, it couldn't be cancelled if the user continued speaking
3. **No speech detection during pause**: The system didn't check if the user resumed speaking during the wait period

## Solution Implemented

### 1. Increased Default Pause Duration
- Changed default `post_speech_pause_ms` from **250ms to 1200ms** (1.2 seconds)
- This allows users to take natural pauses without being interrupted
- Configurable via environment variable `POST_SPEECH_PAUSE_MS`

### 2. Smart Pause with Cancellation
The `_finalize_pending_final()` method now:
- Waits in **100ms chunks** instead of one long sleep
- **Checks every 100ms** if the user has started speaking again
- **Cancels the response** if new speech is detected
- **Resets the timer** if speech is detected during the pause
- **Verifies silence** at the end before responding

### 3. Speech Tracking
- Added `_last_speech_ts` to track when user last spoke
- Updates on:
  - VAD speech start detection
  - Any speech activity (non-silent frames)
  - Final STT transcripts
- Used to detect if user resumed speaking during pause

### 4. Automatic Cancellation
- When user starts speaking again (VAD detects speech), pending finalization is immediately cancelled
- Prevents responses from starting if user continues their thought

## Code Changes

### web_session.py
1. **Default pause increased**: `post_speech_pause_ms: int = 1200`
2. **Added speech tracking**: `self._last_speech_ts: float = 0.0`
3. **Enhanced `_finalize_pending_final()`**: Now checks for speech every 100ms
4. **Automatic cancellation**: Cancels pending finalization when speech detected

### web_app.py
1. **Added configurable option**: `POST_SPEECH_PAUSE_MS` environment variable
2. **Passes to session**: `post_speech_pause_ms=post_speech_pause_ms`

## Configuration

You can adjust the pause duration via environment variable:
```bash
export POST_SPEECH_PAUSE_MS=1500  # 1.5 seconds (more conservative)
export POST_SPEECH_PAUSE_MS=1000  # 1.0 seconds (faster response)
export POST_SPEECH_PAUSE_MS=2000  # 2.0 seconds (very patient)
```

## Behavior Now

1. **User speaks**: System listens and transcribes
2. **User pauses**: System waits 1.2 seconds (configurable)
3. **During pause**: System checks every 100ms if user resumed speaking
4. **If user continues**: Timer resets, response cancelled
5. **After sustained silence**: System responds only after full pause period + silence verification

## Testing

To verify the fix works:
1. Speak with natural pauses (e.g., "Hello... um... I need help with... my payment")
2. System should wait for you to finish before responding
3. If you continue speaking after a pause, system should wait longer
4. Check logs for `finalize_cancelled` events to see when responses are cancelled

## Log Events

New log events to monitor:
- `finalize_cancelled` with reasons:
  - `"pending_cleared"`: Pending final was cleared externally
  - `"user_speaking"`: User started speaking again during pause
  - `"not_in_silence"`: User still speaking after pause period

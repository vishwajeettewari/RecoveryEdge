# Current Task

- [x] Review the latest reported call transcript and logs to isolate the remaining failures in identity acknowledgement, refusal handling, and post-closing recovery.
- [x] Fix explicit name reconfirmation so mixed-script name capture is acknowledged by speaking the borrower name back, and follow-up prompts do not consume "did you hear my name?" as awareness/payment answers.
- [x] Add a refusal-resolution path for utterances like "call back anytime but I won't pay" so the agent acknowledges resistance, explains the need to resolve the loan, and asks for one practical next step instead of looping on callback.
- [x] Reopen the workflow when the borrower says something meaningful after `closing`, so objections, updated PTP dates, or abusive language do not get answered with the same farewell.
- [x] Add regression coverage for the reported Hindi/Punjabi name confirmation, refusal, and post-closing cases.
- [x] Run targeted verification, update `tasks/lessons.md`, and record the review result here.

## Review

- Updated `workflow_engine.py` so explicit name-reconfirmation questions no longer advance awareness/payment steps, Hindi refusal phrases are classified correctly, and refusal responses route to a solution-oriented branch instead of default callback capture.
- Updated `web_session.py` so deterministic prompts explicitly speak the borrower name back when asked, `closing` can reopen to `ask_ptp_or_callback` for meaningful post-close payment talk, and abusive post-close utterances receive a safe terminating response instead of the generic farewell.
- Updated `strategy_engine.py` so dynamic turns use a `resistance_resolution` strategy when the borrower resists payment without hardship/dispute conditions.
- Added regressions in `tests/test_workflow_engine.py` and `tests/test_web_session_guards.py` for name reconfirmation, Hindi refusal handling, post-closing reopen logic, and abusive closing behavior.
- Verification: `python3 -m py_compile workflow_engine.py web_session.py strategy_engine.py tests/test_workflow_engine.py tests/test_web_session_guards.py`
- Verification: `pytest -q tests/test_workflow_engine.py tests/test_web_session_guards.py` -> `137 passed`

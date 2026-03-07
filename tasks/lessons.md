# Lessons

- 2026-03-07: Voice identity confirmation must normalize Unicode punctuation and recover from fragmented STT finals before workflow progression, otherwise mixed-script names can be dropped and the call can loop or stall.
- 2026-03-07: Voice workflow turns must distinguish "please tell me your name" from "am I speaking with X", and awareness denials like "I didn't know" must trigger an explain-first overdue prompt instead of jumping straight to payment pressure or looping callback requests.
- 2026-03-07: Voice fixes must cover both deterministic prompts and interrupted dynamic LLM turns. If the parser, name acknowledgement, or Hindi voice-gender logic only exists in fixed prompts, barge-ins will bypass it and reintroduce the bug.
- 2026-03-08: Post-identity meta questions like "did you hear my name?" must not be consumed as awareness or payment answers; they need an explicit name-confirmation response and the original workflow step must stay pending.
- 2026-03-08: Once the call reaches `closing`, meaningful payment objections or updated commitments must be rebound to the last payment-resolution step, while abusive language should get a dedicated safe-exit response instead of the generic farewell loop.

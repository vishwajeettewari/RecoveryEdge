# Voice Agent Validation Report

## Updated Architecture

Audio Input -> Streaming STT -> Intent Classifier -> Entity Extractor -> Sentiment Detector -> Dialogue State Manager -> Language Detection (gated) -> LLM Response Generator -> Streaming TTS

## Audit Summary

- Root cause for repeated-question loops: payment-state overrides and prompt repetition handling were not tied to workflow state.
- Root cause for identity leakage: a newly captured name was treated as confirmed identity instead of requiring a second explicit confirmation turn.
- Root cause for language errors: script detection was being treated as language intent without confidence, utterance-length, or entity gating.
- Root cause for barge-in failures: interruption detection was separated from intent/state updates, so corrections and payment commitments did not override the live script cleanly.

## Scenario Results

- Passed scenarios: 10/10
- No repeated prompts across all passing scenarios: True
- No payment-question relapse after unpaid across all passing scenarios: True

### PASS `borrower_unaware_of_loan`
- Final step: `closing`
- Payment made: `False`
- PTP date: `2026-03-13`
- Reference number: `None`
- Language offers: `[]`
- Interruption override: `False`

### PASS `borrower_already_paid`
- Final step: `closing`
- Payment made: `True`
- PTP date: `None`
- Reference number: `1234567890`
- Language offers: `[]`
- Interruption override: `False`

### PASS `borrower_promises_payment`
- Final step: `closing`
- Payment made: `False`
- PTP date: `2026-03-14`
- Reference number: `None`
- Language offers: `[]`
- Interruption override: `False`

### PASS `borrower_speaks_punjabi`
- Final step: `closing`
- Payment made: `False`
- PTP date: `2026-03-13`
- Reference number: `None`
- Language offers: `['pa-IN', 'pa-IN']`
- Interruption override: `False`

### PASS `borrower_mixes_hindi_and_punjabi`
- Final step: `closing`
- Payment made: `False`
- PTP date: `2026-03-13`
- Reference number: `None`
- Language offers: `[]`
- Interruption override: `False`

### PASS `borrower_interrupts_agent`
- Final step: `closing`
- Payment made: `False`
- PTP date: `2026-03-13`
- Reference number: `None`
- Language offers: `[]`
- Interruption override: `True`

### PASS `borrower_abuses_agent`
- Final step: `closing`
- Payment made: `None`
- PTP date: `None`
- Reference number: `None`
- Language offers: `[]`
- Interruption override: `False`

### PASS `borrower_changes_answer_mid_conversation`
- Final step: `closing`
- Payment made: `False`
- PTP date: `2026-03-14`
- Reference number: `None`
- Language offers: `[]`
- Interruption override: `True`

### PASS `borrower_partial_payment_promise`
- Final step: `closing`
- Payment made: `False`
- PTP date: `2026-03-13`
- Reference number: `None`
- Language offers: `[]`
- Interruption override: `False`

### PASS `borrower_refuses_to_pay`
- Final step: `closing`
- Payment made: `False`
- PTP date: `None`
- Reference number: `None`
- Language offers: `[]`
- Interruption override: `False`

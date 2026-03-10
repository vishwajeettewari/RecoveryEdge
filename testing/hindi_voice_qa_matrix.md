# Hindi Voice Agent QA Matrix

Use this sheet for typed-turn QA first and then for voice-call QA with the same scripts.

For the full adversarial and red-team catalog, use [hindi_voice_redteam_library.md](/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1/testing/hindi_voice_redteam_library.md) and [hindi_voice_scenarios.json](/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1/testing/hindi_voice_scenarios.json).

## How to Use

1. Upload `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1/data/sample_portfolio_collections_dashboard.csv` and launch a demo campaign.
2. Open the calling console for the seeded task/customer.
3. Run the scenario turn-by-turn in Hindi or Hinglish.
4. Save the outcome where applicable.
5. Verify backend outcome rows, follow-up rows, dashboard deltas, and operations copilot grounding.

## Scenario Matrix

| Scenario ID | Customer Script | Expected Branch | Expected Saved Outcome | Expected Metric / Dashboard Effect |
| --- | --- | --- | --- | --- |
| `HI-01` | `हाँ` -> `हाँ, मैं राहुल शर्मा बोल रहा हूँ` -> `मुझे पता नहीं था` -> `मेरी नौकरी चली गई है, अभी पैसे नहीं हैं` -> `कल 5 बजे कॉल कर लीजिए` | consent -> identity -> awareness denied context -> hardship -> callback capture | `disposition=callback_requested/closing`, `callback_time=17:00`, hardship context retained | callback count increases, follow-up scheduled, discipline widgets show callback work queue |
| `HI-02` | `हाँ` -> `हाँ` -> `हाँ, पता है` -> `मैंने पेमेंट कर दिया है` -> `UTR 1234567890 है` | payment-made branch -> UTR capture -> close | `payment_made=true`, `reference_number=1234567890`, no PTP/callback | paid/ref verification path visible in backend, no new callback/PTP follow-up |
| `HI-03` | `गलत नंबर है` | wrong-party close from identity step | `disposition=wrong_party` | wrong-party outcome visible in backend, campaign health reflects non-contact/non-right-party resolution |
| `HI-04` | `नमस्ते` at consent step, then `हाँ` | consent unclear repair -> consent capture | no final outcome yet | verifies consent discipline and that the agent does not skip consent on ambiguous greeting |
| `HI-05` | `दो दिन में` after uncertainty prompt, then `दो दिन में पेमेंट कर दूँगा` | ambiguity repair -> PTP clarification -> PTP capture | `ptp_date=<normalized ISO date>` | PTP count increases, follow-up discipline variables populate, commitment widgets update |
| `HI-06` | `सैलरी लेट है, अभी pay nahi kar paunga` | hardship + inability -> callback/solution prompt | no final commitment until callback/PTP given | hardship-aware prompting, no aggressive payment pressure |
| `HI-07` | `मुझे कॉल मत करिए` | DND close | `disposition=dnd_requested` | backend reflects suppression intent; no further calling action should be proposed |
| `HI-08` | abuse during close: `तुम लोग बेकार हो, बंद करो` | abusive-language guard -> safe close | `last_transition_reason=abusive_language` | compliance / exception counts update, no further collection pressure in response |
| `HI-09` | `कल 11 बजे call kariye` | callback capture with mixed Hindi/English | `callback_time=11:00` | callback metrics and follow-up scheduling update |
| `HI-10` | `पेमेंट नहीं हुआ, अगले सोमवार कर दूँगा` | unpaid -> PTP capture | `ptp_date=<next Monday ISO date>` | PTP and expected recovery metrics increase |

## Backend Checks

- Verify the latest row in `outcomes` contains `session_id`, `campaign_id`, `disposition`, `ptp_date`, `callback_time`, `reference_number`, and timestamps where applicable.
- Verify `followups` contains `callback_due` or the PTP reminder set after commitment capture.
- Verify `excel_sink` output only when the relevant save path is exercised in the calling flow.

## Dashboard Checks

- Operations overview should reflect updated contact coverage, PTP/callback counts, and follow-up discipline after refresh/poll.
- Risk and portfolio views should only move on risk metrics that actually depend on DPD snapshots or commitment outcomes.
- Missed-PTP, callback queue, and commitment widgets should change only when the saved outcome justifies it.

## Ops Copilot Checks

- Ask: `Which campaign needs attention and why?`
- Ask: `Show me risks for callbacks and missed commitments in this campaign.`
- Ask: `What experiment should I run for this campaign?`
- Ask: `Can you change the strategy for this bucket?`

Expected:

- The copilot cites campaign metrics/evidence instead of generic text.
- Experiment launch suggestions are concrete and action-oriented.
- Strategy changes go through approval-aware flow rather than silent mutation.

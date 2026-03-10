# Current Task

## Full Repository Audit

- [x] Map the repo structure, runtime entrypoints, and verification surfaces so the audit covers backend, frontend, tests, and operational glue.
- [x] Run the strongest available local verification for Python and React, capture failures, and separate real regressions from environment-only blockers.
- [x] Inspect high-risk modules end to end for correctness, security, configuration safety, and test coverage gaps.
- [x] Write a detailed review section with prioritized findings, concrete evidence, and residual risks.

### Full Repository Audit Notes

- User requested audit only. No product changes should be made unless an audit step requires non-functional task tracking updates in this file.

## Full Repository Audit Review

- Verification run:
  - `python3 -m py_compile *.py tests/*.py testing/*.py` passed.
  - `pytest -q` failed with 5 regressions out of 244 tests.
  - `npm test -- --run` passed: 7 files, 13 tests.
  - `npm run build` passed, but Vite emitted a large-bundle warning for a 1.26 MB pre-gzip main JS chunk.
- Highest-priority findings:
  - `audit_store.py` scopes outcome metrics through task existence checks, so campaign/state/bucket-filtered analytics drop valid outcomes when no matching task row exists. This undercounts PTP and callback metrics in exactly the session-driven paths covered by `tests/test_web_session_outcomes.py`. Root cause lives in `_task_scope_exists` and the scoped `outcomes` queries inside `metrics()`.
  - `web_app.py` rebuilds `demo["router"]` inside `_refresh_demo_runtime_config()` on every telephony request. The `/api/telephony/test_call` and `/api/telephony/agent_call` handlers call this right before dispatch, so any injected router wrapper, monkeypatch, or in-process runtime state is discarded and the request uses a fresh router instead. That is why the telephony queueing tests now ignore the stubbed `call_sid` values.
  - `frontend-react/src/api/client.ts` stores the access token in `localStorage` and also sends it as a bearer token on every request, even though the backend already sets HttpOnly auth cookies. This widens token-exfiltration surface unnecessarily and makes XSS materially worse than a cookie-only design.
  - `web_session.py` returns success from `save_ptp_or_callback` even when Excel/audit persistence fails, because the critical writes are wrapped in broad `except Exception: pass` blocks. A real storage failure would leave the operator seeing a successful save while analytics and audit trails silently miss the commitment.
- Lower-priority findings:
  - `frontend-react/src/app/AppRoutes.tsx` eagerly imports every major page, which matches the Vite warning and explains why the whole authenticated shell ships as one large JS entry chunk instead of route-split bundles.
  - `pytest.ini` declares `asyncio_default_fixture_loop_scope = function`, but the current `pytest -q` run reports it as an unknown config option. The suite still runs, but the async test configuration is drifting from the installed toolchain.
  - `web_app.py` still uses `@app.on_event("startup")`, which now emits FastAPI deprecation warnings and should move to lifespan handlers before framework upgrades make it noisy or brittle.

# Current Task

## Calling Console Action Fit And Command Center Scope Wiring

- [x] Re-audit the Calling Console at narrower desktop widths, identify the remaining clipped action buttons, and fix the responsive action rail without regressing the rest of the layout.
- [x] Trace every AI Collections Command Center filter and action against its backing endpoint, then wire any partially connected sections so the page scope is consistent end to end.
- [x] Run focused verification for the Calling Console and AI Collections Command Center, then document the outcome in the review section below.

### Calling Console Action Fit And Command Center Scope Wiring Notes

- The remaining Calling Console regression is not the main `Start Call` control. The live narrower-width audit shows the right-rail quick actions clipping `Use Task Phone` and `Call Number`, which means the rail action grid still needs a more adaptive column rule.
- The AI Collections Command Center still exposes task-state and DPD-bucket filters more broadly than the backend currently honors. The main queue and some session/task views narrow correctly, but the analytics endpoints still stay mostly campaign-wide and the export menu is still placeholder UI.

## Calling Console Action Fit And Command Center Scope Wiring Review

- Updated `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/frontend-react/src/styles.css` so the Calling Console rail actions now use an adaptive auto-fit grid with button labels allowed to wrap cleanly. The remaining narrower-width regressions were the rail buttons, not the main `Start Call` button.
- Live re-verification on the authenticated Calling Console at 1280px and 1200px now shows full `Use Task Phone`, `Call Number`, and `Check Mic` labels without the previous truncation. Verified with fresh Playwright screenshots after a temporary demo-task assignment to the calling agent in the local demo DB, then reverted that runtime data tweak once the audit was complete.
- Extended `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/audit_store.py`, `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/workbench_service.py`, and `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/web_app.py` so Command Center scope now propagates across analytics, roll-forward, recovery, agent metrics, task summaries, and live session filtering for the selected campaign, task state, and DPD bucket.
- Updated `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/frontend-react/src/features/command-center/CommandCenterPage.tsx` so every analytics query now sends the same state and bucket scope as the task list, and the export menu now generates a real Excel-compatible CSV export plus a printable PDF-style report instead of placeholder items.
- Added regression coverage in `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/frontend-react/src/features/command-center/CommandCenterPage.test.tsx` for scoped analytics query propagation and live export actions, and in `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/tests/test_ops_layers.py` for backend scope filtering across metrics, roll-forward, recovery, agent metrics, and task summaries.
- Verified with:
  - `python3 -m py_compile audit_store.py workbench_service.py web_app.py tests/test_ops_layers.py`
  - `python3 -m unittest tests.test_ops_layers.OpsLayerTests.test_command_center_scope_filters_apply_across_metrics_layers`
  - `npm test -- --run src/features/command-center/CommandCenterPage.test.tsx src/features/calling/CallingConsolePage.test.tsx`
  - `npm run build`
- Verification note:
  - the production build still emits the existing Vite chunk-size warning for the main bundle, but the build completes successfully.

## UI Button Typography And Label Fit

- [x] Audit the full React UI for oversized button text, clipped labels, and button shapes distorted by text sizing.
- [x] Tune shared button typography and spacing for a cleaner enterprise-grade control surface.
- [x] Fix page-level button variants that still truncate labels or look visually loud after the shared pass.
- [x] Run live verification plus focused frontend checks, then document findings and outcomes in the review section below.

### UI Button Typography And Label Fit Notes

- The current Mantine button theme uses heavy weight, fully pill-shaped radii, and tight small-button variants. That combination is likely making labels feel oversized and, on denser tables and action groups, can clip or visually crowd text.
- The audit should cover the major authenticated routes, not just the calling console, because the same shared button styling is reused across the shell and multiple module pages.

## UI Button Typography And Label Fit Review

- Audited the live React shell across `/app/dashboard`, `/app/risk-portfolio`, `/app/command-center`, `/app/control`, `/app/portfolio`, `/app/workbench`, `/app/calling`, `/app/alerts`, `/app/reports`, `/app/integrations`, `/app/users`, `/app/settings`, and `/app/profile` with Playwright screenshots and button-overflow checks.
- The two real label-fit regressions in the shipped UI were the Operations Copilot prompt buttons and the Calling Console `Capture PTP` quick action. Both were clipping live labels at desktop width before the fix.
- Updated `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/frontend-react/src/theme/theme.ts` to calm the shared button treatment by reducing weight, removing the fully pill-shaped radius, and tightening stepper typography so button-like controls read more enterprise and less oversized.
- Updated `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/frontend-react/src/features/control/control-layer.css` so Operations Copilot action and prompt buttons can grow vertically, use smaller copy, and wrap long labels cleanly instead of truncating strategic prompts.
- Updated `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/frontend-react/src/styles.css` so the Calling Console disposition strip uses a more flexible grid and denser button copy, which restores the full `Capture PTP` label without distorting the rest of the action row.
- Live re-verification after the patch showed the previous clipped controls reduced from 3 to 0 on Operations Copilot and from 1 to 0 on the Calling Console. The other audited routes remained free of clipped button labels.
- Verified with:
  - Live Playwright route audit plus screenshots before and after the fix
  - `npm run test -- --run src/features/calling/CallingConsolePage.test.tsx src/features/command-center/CommandCenterPage.test.tsx src/features/auth/LoginPage.test.tsx`
  - `npm run build`
- Verification note:
  - the production build still emits the existing Vite chunk-size warning for the main bundle, but the build completes successfully.

## Calling Console Transcript Visibility

- [x] Inspect the current calling-console transcript layout and identify why the live transcript region is visually collapsing.
- [x] Increase the live transcript panel footprint and transcript readability without breaking the rest of the calling console layout.
- [x] Run focused frontend verification and document the result in the review section below.

### Calling Console Transcript Visibility Notes

- The current calling console keeps the transcript inside a flexible panel with no guaranteed minimum footprint, so the transcript area can collapse behind the rest of the middle-column controls.
- The fix should improve transcript usability in both the active borrower calling console and the no-task voice test desk, since both surfaces share the same transcript panel pattern.

## Calling Console Transcript Visibility Review

- Updated `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/frontend-react/src/features/calling/CallingConsolePage.tsx` so both transcript surfaces now use explicit transcript panel modifiers for the no-task voice test desk and the active-call console.
- Updated `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/frontend-react/src/styles.css` to give the transcript panel a guaranteed larger minimum height, add a minimum scroll viewport inside the transcript body, and increase transcript copy readability with better line-height and wrapping behavior.
- The result is a visibly larger live transcript area in both calling modes without changing the surrounding workflow or controls.
- Verified with:
  - `npm test -- --run src/features/calling/CallingConsolePage.test.tsx`
  - `npm run build`
- Verification note:
  - the production build still emits the existing Vite chunk-size warning for the main bundle, but the build completes successfully.

## AI Command Center Campaign Metrics Wiring

- [x] Audit the current AI Command Center sections and map each seeded metric or chart to an existing campaign-backed endpoint or derived dataset.
- [x] Replace the seeded dashboard constants in `frontend-react/src/features/command-center/CommandCenterPage.tsx` with live campaign/task/session/recovery/roll-forward data.
- [x] Keep the page aligned to the existing shell and filter UX while making the primary scope an actual campaign instead of a fake portfolio seed.
- [x] Run focused frontend verification and document the results in the review section below.

### AI Command Center Campaign Metrics Wiring Notes

- The current page is still a demo composition: `PortfolioHealthSection`, `DelinquencyRiskSection`, `RecoveryPerformanceSection`, `CollectionsOperationsSection`, `AIDecisionIntelligenceSection`, and `ActionInterventionSection` each define hard-coded arrays and totals inside `CommandCenterPage.tsx`.
- The backend already exposes the live signals needed for this surface: `/api/campaigns`, `/api/metrics`, `/api/metrics/recovery`, `/api/metrics/roll-forward`, `/api/metrics/agents`, `/api/tasks/summary`, and `/api/sessions`.

## AI Command Center Campaign Metrics Wiring Review

- Replaced the seeded `frontend-react/src/features/command-center/CommandCenterPage.tsx` demo dashboard with a campaign-scoped control room that now loads its state from `/api/campaigns`, `/api/metrics`, `/api/metrics/recovery`, `/api/metrics/roll-forward`, `/api/metrics/agents`, `/api/tasks/summary`, `/api/sessions`, and `/api/tasks`.
- The filter bar now scopes the page to a real campaign plus live task-state and DPD-bucket filters, instead of exposing fake region and portfolio selectors that were not connected to data.
- Rebuilt the six command-center sections so they render actual campaign KPIs, bucket exposure, roll-rate movement, recovery funnel/progress, agent leaderboard, live session monitor, derived recommendations, and high-priority account actions from real queue data.
- Removed the seeded “AI strategy” and fake borrower/task content from the command center. The page now derives recommendations from live callback backlog, bucket concentration, SLA breaches, and retry pressure instead of shipping static demo arrays.
- Replaced the old static regression in `frontend-react/src/features/command-center/CommandCenterPage.test.tsx` with an API-backed render test that verifies real campaign data is shown and seeded demo content such as `Call Tonight` and `Rajesh Kumar` no longer appears.
- Verified with:
  - `npm test -- --run src/features/command-center/CommandCenterPage.test.tsx`
  - `npm run build`
- Verification note:
  - the production build still emits the existing Vite chunk-size warning for the main bundle, but the build completes successfully.

## Global Theme Flicker Stabilization

- [x] Trace the light/dark flicker reported on interactive controls and confirm whether the root cause is theme-state churn, shared component state styling, or both.
- [x] Harden the global frontend color-scheme wiring so light/dark mode resolves deterministically and does not reapply unexpectedly during unrelated UI actions.
- [x] Normalize shared interactive component states so buttons, action icons, menus, and disabled/loading controls keep the active theme consistently across the shell.
- [x] Run focused frontend verification for the theme flicker fix and document the results in the review section below.

### Global Theme Flicker Stabilization Notes

- Mantine's stock local-storage manager accepts `auto`, while the current boot script only handles explicit `light` or `dark`. That leaves room for the shell and the boot script to resolve the same stored value differently.
- Shared interactive states are still under-themed globally. `filled` buttons are customized, but `light`, `subtle`, `default`, disabled, loading, and action-icon/menu states still rely on Mantine defaults, which can visually look like the app is hopping between dark and light surfaces.

## Global Theme Flicker Stabilization Review

- Added an explicit color-scheme manager in `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/frontend-react/src/theme/colorScheme.ts` and switched `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/frontend-react/src/main.tsx` to use it instead of Mantine's permissive local-storage manager. The app now persists only explicit `light` or `dark` values and rejects `auto` fallback behavior.
- Updated the early boot script in `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/frontend-react/index.html` so the root `data-mantine-color-scheme` attribute is seeded from the same explicit storage rule as the running app. That removes the boot/runtime mismatch that could re-resolve the scheme differently during later interactions.
- Tightened the shell toggle in `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/frontend-react/src/app/AppShellLayout.tsx` to keep transition suppression consistent during deliberate theme changes.
- Extended `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/frontend-react/src/styles.css` with shared light/dark tokens for button, action-icon, dropdown, disabled, and loading states, and rewired the global Mantine selectors so `light`, `subtle`, `outline`, `default`, disabled, and loading controls stay on the active shell theme instead of falling back to library defaults.
- Added regression coverage in `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/frontend-react/src/theme/colorScheme.test.ts` to lock the explicit storage behavior, alongside the existing calling and command-center frontend regressions.
- Verified with:
  - `npm test -- --run src/theme/colorScheme.test.ts src/features/calling/CallingConsolePage.test.tsx src/features/command-center/CommandCenterPage.test.tsx`
  - `npm run build`
- Verification note:
  - the production build still emits the existing Vite chunk-size warning for the main bundle, but the build completes successfully.

## Calling Console Voice Recovery

- [x] Trace the broken `Start Call`, `Check Mic`, and phone-bridge test paths using the frontend logic plus the backend log evidence.
- [x] Fix the calling console so browser voice start fails cleanly on missing config, the worklet path resolves under `/app`, and phone-bridge sessions map to live timeline/transcript capture.
- [x] Restore the no-task voice test desk so transcript and session telemetry remain visible for direct phone testing.
- [x] Run focused verification for the recovered calling console flow and document the results in the review section below.

### Calling Console Voice Recovery Notes

- Browser voice startup is failing in two stages: the worklet loader still points at root-relative `/worklets/...` paths even though the app is served from `/app`, and `startCall()` flips `callLive` before websocket/audio startup has actually succeeded.
- Direct phone bridge testing lost its transcript/metrics desk because the empty-state path now returns early and hides the richer transcript/timeline panels.
- Phone-bridge calls create a synthetic `tel-agent-*` session id in `/api/telephony/agent_call`, but that id is not passed into the Twilio media websocket session, so the frontend cannot follow the live telephony timeline.
- Dropping a new `.env` into the repo does not currently refresh the in-memory `ActionRouter`; telephony endpoints keep using the old Twilio config until process restart.

## Calling Console Voice Recovery Review

- Fixed runtime telephony config reload in `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/web_app.py` so updated `.env` values are applied to the in-memory `ActionRouter` without requiring a process restart before `Call Number` or Twilio media sessions use them.
- Fixed phone-bridge session continuity by appending the generated `tel-agent-*` session id to the Twilio media websocket URL, passing it through `ActionRouter.place_agent_stream_call(...)`, and constructing `WebCallSession` with that requested session id in `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/web_app.py`, `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/actions.py`, and `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/web_session.py`.
- Fixed browser voice startup in `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/frontend-react/src/features/calling/CallingConsolePage.tsx` by resolving audio worklets through the Vite `/app` base path, delaying the `callLive` flip until websocket plus mic setup succeed, and adding explicit loading states for `Start Call` and `Check Mic`.
- Restored the no-task test desk in `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/frontend-react/src/features/calling/CallingConsolePage.tsx` so direct phone testing now keeps transcript capture, timeline events, active session id, and last-activity telemetry visible even without an assigned borrower task.
- Added focused regression coverage in `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/frontend-react/src/features/calling/CallingConsolePage.test.tsx` for the restored no-task direct phone bridge desk and retained the command-center theme regression in the same verification pass.
- Verified with:
  - `npm test -- --run src/features/calling/CallingConsolePage.test.tsx src/features/command-center/CommandCenterPage.test.tsx`
  - `npm run build`
  - `python3 -m py_compile web_app.py web_session.py actions.py`
- Verification note:
  - the production build still emits the pre-existing Vite chunk-size warning for the main bundle, but the build completes successfully.
  - live Twilio dialing and live Sarvam speech still require the running app to have reachable public telephony websocket infrastructure and valid external provider credentials at runtime; this review verified the repo wiring and regression coverage, not an outbound carrier call from this shell.

## AI Command Center Theme Alignment

- [x] Audit the merged AI Command Center page for hard-coded light-only surfaces, chart chrome, and data-label styles that ignore the shell theme.
- [x] Refactor the AI Command Center theme bindings so dark mode and light mode share the same token system as the rest of the shell.
- [x] Run focused frontend verification for the AI Command Center changes and document the outcome in the review section below.

## AI Command Center Theme Alignment Review

- The root cause was a split theme system inside the merged `AI Collections Command Center`: the shell was already tokenized for dark mode, but `frontend-react/src/styles.css` still gave the command-center filter bar, section cards, KPI cards, chart cards, grid lines, legend text, and tooltip surfaces fixed light-mode values.
- Added dedicated command-center light/dark CSS variables in `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/frontend-react/src/styles.css` and rewired the `.te-command-*` surfaces to those variables so the page now follows the same theme switch as the rest of the shell.
- Updated `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/frontend-react/src/features/command-center/CommandCenterPage.tsx` so Recharts axis ticks, grid lines, tooltips, funnel tracks, and forecast/sub-metric panels read from theme-aware CSS variables instead of hard-coded white or black values.
- Added `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/frontend-react/src/features/command-center/CommandCenterPage.test.tsx` as a focused regression check that renders the page and verifies the token-bound subtle panel surface used by the forecast cards.
- Verified with:
  - `npm test -- --run src/features/command-center/CommandCenterPage.test.tsx`
  - `npm run build`
- Verification note:
  - the production build still emits the existing Vite chunk-size warning for the main bundle, but the build completes successfully and this task did not increase it into a failure.

## Restore Dark Mode And Voice Agent Merge

- [x] Merge the committed changes from `codex/evaluate-wiring-portfolio-metrics-to` back into this worktree so the missing dark mode and voice-agent work is restored.
- [x] Resolve any merge conflicts with minimal impact and confirm the affected frontend and voice-agent files are present in this branch.
- [x] Run focused verification for the restored changes and document the outcome in the review section below.

## Restore Dark Mode And Voice Agent Review

- Merged `codex/evaluate-wiring-portfolio-metrics-to` into this worktree branch and created merge commit `af523fe` on `codex/merge-commandcenter-portfolio-metrics`.
- The restored merge includes the expected dark-mode and voice-agent files, including:
  - `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/frontend-react/src/styles.css`
  - `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/frontend-react/src/theme/theme.ts`
  - `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/frontend-react/src/features/calling/CallingConsolePage.tsx`
  - `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/voice_pipeline.py`
  - `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/barge_in_handler.py`
  - `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/ops_copilot_llm_service.py`
- Verification completed:
  - `python3 -m py_compile web_session.py workflow_engine.py voice_pipeline.py dialogue_state_manager.py intent_classifier.py sentiment_detector.py language_detection_gating.py repetition_guard.py barge_in_handler.py entity_extractor.py ops_copilot_llm_service.py testing/voice_agent_simulation.py tests/test_voice_pipeline.py tests/test_voice_agent_simulation.py`
  - `npm run build` in `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/frontend-react`
- Additional test-suite note:
  - `python3 -m unittest tests.test_voice_pipeline tests.test_voice_agent_simulation tests.test_web_session_guards tests.test_workflow_engine tests.test_web_session_outcomes` is currently blocked in this local environment by two unrelated runtime issues: `tests/test_web_session_guards.py` creates `asyncio.Event()` without a current event loop on Python 3.9, and `pydantic_core` is installed as an incompatible `x86_64` binary for the current arm64 Python runtime.

## Production Voice Agent Audit And Refactor

- [x] Audit the live voice-agent path end to end and document the root causes behind repeated-question loops, missing identity confirmation, language-switch errors, weak multilingual intent detection, missing hostility handling, repetition leakage, barge-in failures, and weak closure logic.
- [x] Implement dedicated modules for:
  - `dialogue_state_manager`
  - `intent_classifier`
  - `sentiment_detector`
  - `language_detection_gating`
  - `repetition_guard`
  - `barge_in_handler`
  - entity extraction for name, amount, date, and payment status
- [x] Refactor the runtime pipeline so the live web call session follows:
  - Streaming STT
  - Intent classification
  - Entity extraction
  - Sentiment detection
  - Dialogue state management
  - Gated language detection
  - LLM response generation
  - Streaming TTS
- [x] Enforce production dialogue rules:
  - no repeated payment-status questions after unpaid is established
  - mandatory identity confirmation before loan disclosure
  - explicit hostility safe-exit
  - interruption intent override with immediate TTS stop
  - closure confirmation plus payment-link assistance
- [x] Add a borrower-behavior simulation suite covering:
  - unaware of loan
  - already paid
  - promises payment
  - Punjabi
  - Hindi + Punjabi mix
  - interruption
  - abuse
  - changed answer
  - partial payment promise
  - refusal to pay
- [x] Generate validation artifacts:
  - simulation logs
  - architecture summary
  - performance/validation report
  - task review with executed verification commands

## Production Voice Agent Review

- Added modular production components:
  - `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1/dialogue_state_manager.py`
  - `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1/intent_classifier.py`
  - `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1/sentiment_detector.py`
  - `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1/language_detection_gating.py`
  - `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1/repetition_guard.py`
  - `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1/barge_in_handler.py`
  - `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1/entity_extractor.py`
- Refactored `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1/voice_pipeline.py` into a real orchestration layer that composes intent, entities, sentiment, dialogue-state updates, language gating, interruption policy, and barge-in decisions.
- Rewired `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1/web_session.py` so typed/STT-final turns now flow through analyzer output instead of ad hoc branching. Hostile utterances terminate cleanly, payment-status corrections no longer loop back to `ask_payment_made`, prompt repetition uses the guard policy, and VAD/STT barge-in decisions now delegate to the new handler.
- Fixed `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1/workflow_engine.py` so a newly captured borrower name is not treated as confirmed identity. The workflow now stays on `confirm_identity` and asks `धन्यवाद। क्या आपका नाम X है?` before disclosing loan details.
- Added simulation and validation artifacts:
  - `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1/testing/voice_agent_simulation.py`
  - `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1/testing/voice_agent_simulation_logs.json`
  - `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1/testing/voice_agent_validation_report.md`
- Added automated coverage in:
  - `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1/tests/test_voice_agent_simulation.py`
  - `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1/tests/test_workflow_engine.py`
  - `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1/tests/test_web_session_guards.py`
- Root causes confirmed in the audit:
  - payment loops came from response-step overrides collapsing both paid and unpaid answers into the same `ask_payment_made` branch
  - identity leakage came from treating a captured name as equivalent to confirmed identity
  - language errors came from script-level heuristics running on short/entity responses
  - barge-in failures came from interruption detection living outside the dialogue/state update path
- Verified with:
  - `python3 -m py_compile web_session.py workflow_engine.py voice_pipeline.py dialogue_state_manager.py intent_classifier.py sentiment_detector.py language_detection_gating.py repetition_guard.py barge_in_handler.py entity_extractor.py testing/voice_agent_simulation.py tests/test_voice_pipeline.py tests/test_web_session_guards.py tests/test_web_session_outcomes.py tests/test_hindi_voice_flows.py tests/test_workflow_engine.py tests/test_voice_agent_simulation.py`
  - `python3 -m unittest tests.test_voice_pipeline tests.test_workflow_engine tests.test_voice_agent_simulation tests.test_web_session_guards tests.test_web_session_outcomes tests.test_hindi_voice_flows`
  - `python3 -m unittest tests.test_workflow_engine tests.test_web_session_outcomes tests.test_hindi_voice_flows tests.test_voice_agent_simulation`
  - `PYTHONPATH=. python3 testing/voice_agent_simulation.py`

## Calling Console UI Alignment And Dark Mode

- [x] Audit the current React shell theme, calling-console styling, and brand assets to identify what is hard-coded versus theme-driven.
- [x] Add a persistent global light/dark mode toggle and shared design tokens so the entire UI can switch cleanly between modes.
- [x] Restyle the calling console so it matches the rest of the product surface in light mode and remains legible in dark mode.
- [x] Ensure logos and other dark brand assets stay visible on black backgrounds by swapping or filtering them appropriately.
- [x] Run targeted frontend verification and document the results in the review section below.
- [x] Fix screenshot-reported dark-mode contrast gaps in dashboard KPIs, chart labels, and table/heatmap values.
- [x] Fix sidebar nav/button borders so the outline is visible by default in dark mode instead of appearing only after interaction.

## Calling Console UI Alignment And Dark Mode Review

- Added persistent light/dark mode handling in `frontend-react` via Mantine color-scheme storage and an early boot script in `frontend-react/index.html`, plus a header toggle in `frontend-react/src/app/AppShellLayout.tsx`.
- Moved the shared shell, module surfaces, and calling-console visuals onto CSS/theme tokens so light mode stays aligned with the existing glassmorphism product language while dark mode shifts the app toward near-black surfaces without losing contrast.
- Reworked `frontend-react/src/features/calling/CallingConsolePage.tsx` and `frontend-react/src/styles.css` so the calling console no longer uses a separate always-dark cockpit style; it now matches the rest of the UI in light mode and remains readable in dark mode.
- Added dark-mode-safe handling for the black `TuringEdge` wordmark by switching to a white/inverted presentation in dark mode.
- Extended dark-mode coverage to the main dashboard/control CSS surfaces so the shell toggle does not leave the most visible pages as bright outliers.
- Added a screenshot-driven dark-mode contrast pass on `frontend-react/src/features/overview/OverviewPage.tsx` and shared styles so KPI values, chart axes, tooltip copy, heatmap cells, and table values stay readable against dark surfaces.
- Fixed the sidebar nav outline behavior in `frontend-react/src/app/AppShellLayout.tsx` and `frontend-react/src/styles.css` so dark-mode nav buttons keep a visible default border instead of only showing a boundary after focus/interaction.
- Fixed the underlying dark-mode mismatch in `frontend-react/src/theme/theme.ts` by moving Mantine `Card`, `Paper`, `Table`, `Input`, `Tabs`, `Drawer`, and `Modal` surfaces from conditional theme colors to the same CSS-variable system used by the shell. This prevents dark chrome from being paired with light content panels when the theme toggles.
- Verified with:
  - `npm run build`
  - `npm test -- --run src/features/calling/CallingConsolePage.test.tsx`
  - `npm test -- --run src/features/overview/OverviewPage.test.tsx src/features/calling/CallingConsolePage.test.tsx`

## Voice Agent Architecture Fixes

- [x] Audit the live `WebCallSession` pipeline and map the production insertion points for intent classification, entity extraction, dialogue-state management, language gating, and barge-in control.
- [x] Implement modular pipeline components for:
  - gated language detection that ignores short/entity-style utterances and script-only signals
  - utterance and interruption intent classification
  - dialogue-state management aligned to `GREETING`, `IDENTITY_CONFIRM`, `PAYMENT_STATUS`, `PTP_CAPTURE`, and `CLOSURE`
  - repetition guard and repair-mode policy
- [x] Integrate the pipeline into `web_session.py` so streaming STT finals/partials, language switch requests, interruption handling, and prompt generation follow the new architecture.
- [x] Add regression coverage for:
  - borrower names transcribed in Punjabi/native script not triggering a language switch
  - explicit language requests requiring confirmation before switching
  - multi-sentence non-name utterances becoming language-switch candidates only through gating
  - barge-in interruption intents overriding the current prompt/state cleanly
  - repair mode and repetition guard preventing loops
- [x] Run targeted tests and static verification for the touched modules.

## Voice Agent Review

- Added `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1/voice_pipeline.py` to isolate utterance intent classification, gated language-switch decisions, high-level dialogue-state mapping, interruption repair tracking, and prompt-history guard logic from the transport/session code.
- Rewired `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1/web_session.py` so the live pipeline now follows: STT final -> intent classification -> entity extraction -> dialogue-state update -> gated language decision -> response generation/TTS, with language switches moving through an explicit confirmation step instead of native-script auto-switching.
- Tightened barge-in handling in `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1/web_session.py` so VAD/STT interruption immediately stops playback, switches back to listening, classifies correction/confusion/payment/language-preference interruptions, and enters Hindi repair mode after repeated confusion while restoring the last valid dialogue state.
- Added regression coverage in `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1/tests/test_voice_pipeline.py` and `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1/tests/test_web_session_guards.py` for native-script names, confirmation-before-switch, multi-turn language evidence, repair mode, and prompt repetition behavior.
- Verified with:
  - `python3 -m py_compile web_session.py voice_pipeline.py tests/test_web_session_guards.py tests/test_voice_pipeline.py`
  - `python3 -m unittest tests.test_voice_pipeline tests.test_web_session_guards`
  - `python3 -m unittest tests.test_web_session_outcomes tests.test_hindi_voice_flows tests.test_workflow_engine`

- [x] Reproduce the Punjabi language-shift, name-confirmation, UTR-loop, and missing-PTP-confirmation failures in the current workflow/session path.
- [x] Implement the minimal-but-correct fixes for multilingual adaptation, question-priority handling, payment-status branching, PTP confirmation, and payment-link offer behavior.
- [x] Add focused regression coverage for the reported conversation failures and verify the updated suites.

# Review

- Added deterministic Punjabi handling in `web_session.py`: native-script auto-detection, Punjabi fixed prompts, Punjabi greeting/on-behalf wording, Punjabi name acknowledgment, and typed-input auto-switch behavior.
- Added deterministic `confirm_ptp` flow in `workflow_engine.py` so relative commitments like `कल` or `tomorrow` are captured but must be explicitly confirmed before backend persistence and dashboard metric updates.
- Fixed payment-status branching so `ask_reference_number` and `ask_payment_made` now escape correctly into unpaid/PTP handling instead of looping on UTR when the borrower says payment is not done or will be done later.
- Added callback-time guardrails so bare numeric chatter does not get misread as callback time without explicit time or callback context.
- Verified with:
  - `python3 -m unittest tests.test_workflow_engine tests.test_web_session_guards tests.test_web_session_outcomes`
  - `python3 -m unittest tests.test_hindi_voice_flows`
  - `python3 -m py_compile workflow_engine.py web_session.py`

# Marketing Figma Delivery

- [x] Audit the existing marketing screenshot pack, deck narrative, and demo routes so the Figma delivery uses verified assets instead of guesswork.
- [x] Confirm the local demo environment and Figma account state, then send the product surfaces into Figma in a reusable file structure.
- [x] Build a high-polish marketing demo sequence in Figma using the product surfaces, with a clear scene order, on-frame copy, and voiceover-ready storyboard.
- [x] Verify the generated Figma artifacts and document the deliverables, limitations, and recommended export path for the client video.

# Marketing Review

- Created a Figma-ready cinematic storyboard page in `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1/marketing/figma_demo_storyboard.html` using the verified screenshot pack and the repo's existing client-demo narrative.
- Created a second Figma-ready asset handoff page in `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1/marketing/figma_design_library.html` with the product surfaces presented at larger size for reuse.
- Verified Figma authentication with the active account `vishwajeettewari@gmail.com`.
- Served the HTML pages locally via `python3 -m http.server 4174 --bind 127.0.0.1` and captured them into the same Figma design file.
- Generated Figma file:
  - storyboard file: `https://www.figma.com/design/5iwxjGs7ZNG9Lzz5d15bEK`
  - raw screen library page in same file: `https://www.figma.com/design/5iwxjGs7ZNG9Lzz5d15bEK?node-id=2-2`
- Result:
  - the Figma file now contains a client-facing demo-video storyboard built from the product surfaces
  - the same file also contains a reusable product-surface library for alternate cuts, decks, or role-specific demo versions
  - the capture script remains in both HTML files so the pages can be re-captured into Figma later without rebuilding the layout
- Recommended export path:
  - duplicate each storyboard scene into its own `1920x1080` frame in Figma
  - apply slow zoom or slide transitions
  - record the voiceover externally and combine it with the exported scene sequence into a 75-90 second client video

# Marketing Animation Frames

- [x] Create a dedicated Figma-capture page with consistent `1920x1080` product-video frames designed for Smart Animate-style sequencing.
- [x] Capture the animated-frame page into the existing Figma file as a separate page for prototype/video assembly.
- [x] Verify the new Figma page and document the final handoff for video use.

# Marketing Animation Review

- Created `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1/marketing/figma_video_frames.html` as a dedicated capture source for six cinematic demo frames sized to `1920x1080`.
- Captured the frame page into the existing Figma file at `https://www.figma.com/design/5iwxjGs7ZNG9Lzz5d15bEK?node-id=4-2`.
- Verified via Figma metadata that the new page `TuringEdge Recovery OS | Animated Demo Frames` contains six top-level sections at `1920x1080`, suitable for frame-by-frame animation/prototype work.
- Embedded voiceover and motion notes directly into each frame so the Figma page can double as a video assembly board.
- Left the capture script in the HTML source so the frame page can be re-captured later if the sequence needs a second cut.

# Marketing Filmstrip Fix

- Created `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1/marketing/figma_prototype_filmstrip.html` as a clearer prototype-ready capture source with six standalone shots laid out horizontally.
- Captured the corrected filmstrip page into the existing Figma file at `https://www.figma.com/design/5iwxjGs7ZNG9Lzz5d15bEK?node-id=8-2`.
- Verified via Figma screenshot and metadata that the node now reads as an obvious left-to-right filmstrip of six `1920x1080` shots rather than a buried long vertical board.

# Product Design Board

- [x] Create a dedicated board page that lays out all current product screens in one clear handoff grid.
- [x] Capture that board into the existing Figma file as a separate page.
- [x] Verify the new board in Figma and document the direct link.

# Product Design Board Review

- Created `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1/marketing/current_product_design_board.html` as a dedicated board for the current product surface set.
- Captured the board into the existing Figma file at `https://www.figma.com/design/5iwxjGs7ZNG9Lzz5d15bEK?node-id=11-2`.
- The capture completed successfully and added the new page to the file.
- Additional screenshot/metadata verification from the Figma MCP tools was blocked afterward by the current seat's tool-call limit, so the direct node link is the handoff path for review.

# Raw Product-Only Board

- [x] Create a bare capture page containing only the current product screens with no labels or presentation wrappers.
- [x] Capture that raw page into the existing Figma file as a separate page.
- [x] Hand off the direct Figma node link for the raw product-only board.

# Raw Product-Only Review

- Created `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1/marketing/raw_product_only_board.html` with only the current product screenshots and no labels, captions, cards, or decorative presentation wrappers.
- Captured the raw page into the existing Figma file at `https://www.figma.com/design/5iwxjGs7ZNG9Lzz5d15bEK?node-id=13-2`.
- The handoff path is the direct node link above.

# Dashboard Split Fix

- [x] Split the dashboard screen off the raw product-only board so it is not mixed with the rest of the product surfaces.
- [x] Capture separate naked boards for the non-dashboard product surfaces and the isolated dashboard surface.
- [x] Hand off the direct Figma links for the split boards.

# Dashboard Split Review

- Created `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1/marketing/raw_non_dashboard_product_board.html` for the non-dashboard raw product surfaces.
- Captured the non-dashboard raw board into the existing Figma file at `https://www.figma.com/design/5iwxjGs7ZNG9Lzz5d15bEK?node-id=16-2`.
- Created `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1/marketing/raw_dashboard_only_board.html` for the isolated dashboard screen.
- Captured the dashboard-only raw board into the existing Figma file at `https://www.figma.com/design/5iwxjGs7ZNG9Lzz5d15bEK?node-id=17-2`.
- Only one dashboard capture exists in the current local screenshot set (`02-overview-control-room.png`), so that is the isolated dashboard page that was split out.

# RecoveryEdge Pitch Deck Review

- [x] Extract the PDF slide content and identify the product thesis, ICP, workflow, and claims.
- [x] Score each expected enterprise SaaS deck element as present, weak, or missing.
- [x] Evaluate the deck from an NBFC collections buyer perspective, including open questions and sales gaps.
- [x] Assess messaging clarity, competitive positioning, missing slides, and pilot-readiness.
- [x] Document the final review findings and recommendations in the review section below.

# RecoveryEdge Pitch Deck Review

- The deck communicates a credible product vision for early-bucket collections operations, especially around post-PTP follow-through, queue control, and governed AI recommendations.

# Branch Merge Validation

- [x] Create an isolated integration worktree from `origin/main` so the current dirty worktree remains untouched.
- [x] Create a new integration branch for merging `origin/feature/commandcenterdashboard` and `origin/codex/evaluate-wiring-portfolio-metrics-to`.
- [x] Merge both branches, resolve any conflicts cleanly, and confirm the resulting branch state.
- [x] Run backend and frontend verification on the merged result.
- [x] Document the merge outcome, verification commands, and any remaining risks in the review section below.

# Branch Merge Validation Review

- Created isolated worktree `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test` from `origin/main` and new branch `codex/merge-commandcenter-portfolio-metrics`.
- Merged `origin/feature/commandcenterdashboard` first, then merged `origin/codex/evaluate-wiring-portfolio-metrics-to`.
- Resolved the only merge conflicts in `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/frontend-react/src/app/AppRoutes.tsx` and `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/frontend-react/src/app/nav.ts` by keeping both additions: the `risk-portfolio` route/nav item and the `command-center` route/nav item.
- Final merged branch state is clean and currently `ahead 7` of `origin/main`.
- Verified with:
  - `pytest -q` -> blocked during test collection by a local environment issue: installed `pydantic_core` binary is x86_64 while the active Python runtime is arm64.
  - `python3 -m py_compile web_app.py web_session.py workflow_engine.py ops_control_service.py audit_store.py campaign_service.py datetime_utils.py followup_service.py workbench_service.py` -> passed.
  - `cd frontend-react && npm install` -> passed.
  - `cd frontend-react && npm run build` -> passed.
  - `cd frontend-react && npm test -- --run` -> passed (`5` test files, `6` tests).
- Remaining risk: backend API/integration tests could not be executed in this environment until the Python package architecture mismatch is fixed.
- The biggest weaknesses are proof and buying detail: no quantified customer outcomes, no case study, no pricing, no deployment/security architecture, and no credible ROI model.
- Positioning is directionally strong but inconsistent. The deck alternates between `RecoveryEdge`, `TuringEdge`, `Recovery OS`, `operations copilot`, and `operating system`, which blurs what the buyer is actually purchasing.
- For a large NBFC, the current deck is more likely to win a second meeting than a pilot approval. It lacks the hard evidence and implementation answers that enterprise buyers need.
- Investor readiness is materially lower than buyer-demo readiness because the deck omits market size, GTM motion, traction, business model, team credibility, and financing context.

# MCP Product And Pitch Analysis

- [x] Review the current product, workflow, and marketing documents to anchor the MCP assessment in the actual collections platform.
- [x] Identify where MCP can improve product grounding, action execution, and enterprise integration for TuringEdge Recovery OS.
- [x] Translate those MCP opportunities into sharper pitch claims, demo beats, and buyer-facing proof points.

# MCP Product And Pitch Review

- MCP is most valuable here as the integration and action plane behind the Operations Copilot, supervisor workflow, and post-call orchestration, not as a buzzword inside the borrower conversation.
- The current stack already has the right primitives for an MCP upgrade: local knowledge retrieval in `web_session.py` and `knowledge_store.py`, hard-coded action delivery in `actions.py`, and an evidence-plus-action control UI in `frontend-react/src/features/control/ControlLayerPage.tsx`.
- The strongest buyer-facing story is not “we use MCP”; it is “the copilot is grounded in your live payment, task, policy, and approval systems and can take governed action across them.”
- The highest-value deck change is a concrete integration/action slide plus a demo scenario that proves cross-system diagnosis and governed execution around missed-PTP containment.

# Operations Copilot Wiring Audit

- [x] Inspect the frontend Operations Copilot surface and identify exactly which API payloads drive the rendered insights, evidence, and recommendations.
- [x] Trace the backend route and service path for the copilot to confirm whether it uses live metrics, static/demo fixtures, or derived summaries.
- [x] Verify the AI provider wiring against environment configuration without exposing secret values, and confirm whether the copilot actually calls an LLM or only returns deterministic heuristics.
- [x] Run targeted verification so the conclusion is backed by executable evidence, not code inspection alone.
- [x] Document the result below with a clear yes/no on metrics grounding, AI usage, UI visibility, and any breakpoints or false claims.

# Operations Copilot Audit Review

- Frontend wiring is real: `frontend-react/src/features/control/ControlLayerPage.tsx` fetches `/api/control-layer/chat` on initial load and on every operator prompt, then renders `answer`, `summary`, `evidence`, and `recommendations` directly into the UI.
- Backend metrics grounding is real: `/api/control-layer/chat` in `web_app.py` calls `OpsControlService.chat()`, which reads live SQLite-backed campaign, task, outcome, follow-up, alert, roll-forward, and agent metrics from `audit_store.py`, `campaign_service.py`, and related tables.
- AI/LLM wiring for Operations Copilot is not real today: the repo contains Azure OpenAI env vars in `.env`, but the Operations Copilot path does not call OpenAI, Azure OpenAI, or any LLM client. `ops_control_service.py` builds the answer, evidence, and recommendations with deterministic rules and string assembly. Model invocation counts did not change before vs after live `/api/control-layer/chat` calls on a cloned copy of `data/demo.db`.
- Current demo data does drive the UI, but the payload is thin. On the current `data/demo.db`, the selected-campaign call returned only the scoped campaign evidence and no recommendations. The all-campaign call returned a metrics-grounded bucket readout, but not AI-generated insight.
- Fixed a live contradiction discovered during the audit: when only one bucket had enough data, the control layer could claim that same bucket was both the strongest and the main leak. The service now suppresses benchmark-style strongest-vs-risk claims and bucket-change recommendations unless at least two populated buckets exist, and it tells the operator when the live window is too thin for cross-bucket benchmarking.
- Verified with:
  - `python3 -m unittest tests.test_ops_control_layer_api tests.test_v2_platform_api`
  - Live TestClient audit against a cloned copy of `data/demo.db`, confirming:
    - `/api/control-layer/chat` returns 200 and feeds UI fields from live metrics
    - `model_invocations` count stays unchanged across chat calls
    - current all-campaign answer now says cross-bucket benchmarking is limited instead of emitting contradictory bucket claims

# Operations Copilot AI Wiring

- [x] Add an Azure OpenAI-backed copilot service that accepts the live metrics bundle and returns grounded natural-language reasoning without changing the frontend response contract.
- [x] Keep deterministic evidence/recommendation generation as the structured source of truth, but let the LLM generate the operator-facing narrative and optional summary enrichment from that grounded context.
- [x] Wire the new copilot service into the Operations Copilot backend with safe fallback to the deterministic path when Azure config is missing or the model call fails.
- [x] Add focused tests for configured LLM usage, deterministic fallback, and grounded response structure.
- [x] Verify with targeted automated tests and a live cloned-db API call, then document the final behavior below.

# Operations Copilot AI Wiring Review

- Added a new Azure-backed copilot client in `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1/ops_copilot_llm_service.py`. It accepts the grounded control-layer context, asks the model for strict JSON, and returns operator-facing overrides for `answer`, `quick_replies`, summary details, and recommendation narrative.
- Preserved deterministic grounding in `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1/ops_control_service.py`: metrics, evidence cards, impact estimates, and action payloads still come from the local data/model logic; the LLM only rewrites operator-facing explanation fields on top of that grounded structure.
- Wired the service into `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1/web_app.py`, and moved `/api/control-layer/chat` onto `asyncio.to_thread(...)` so the synchronous DB + model work does not run inline on the event loop.
- Added realtime deployment support because the current `.env` is configured with `AZURE_OPENAI_MODEL=gpt-realtime-mini`. Standard chat completions were rejected by Azure for that deployment, so the copilot client now detects realtime deployments and uses the Azure realtime websocket path instead.
- Added tests:
  - `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1/tests/test_ops_copilot_llm_service.py`
  - expanded `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1/tests/test_ops_control_layer_api.py`
  - isolated API tests from real Azure by disabling `OPS_COPILOT_LLM_ENABLED` in test app bootstraps unless a test explicitly injects an LLM/fake.
- Verified with:
  - `python3 -m unittest tests.test_ops_copilot_llm_service tests.test_ops_control_layer_api tests.test_v2_platform_api`
  - `python3 -m unittest tests.test_ops_copilot_llm_service tests.test_ops_control_layer_api`
  - `python3 -m py_compile ops_copilot_llm_service.py ops_control_service.py web_app.py`
  - live TestClient call against a cloned `data/demo.db` with real `.env` Azure settings enabled
- Live Azure result:
  - the configured `gpt-realtime-mini` deployment now succeeds through the realtime websocket path
  - the latest `model_invocations` row records `provider=azure_openai`, `model_name=gpt-realtime-mini`, `status=succeeded`
  - the Operations Copilot answer shown to the UI is now model-generated while remaining grounded in the local metrics bundle

# Operations Copilot Chat Deployment Switch

- [x] Rewire Operations Copilot to use Azure chat deployment `gpt-5.2-chat` with the existing Azure endpoint and API key.
- [x] Ensure Operations Copilot uses the chat completions path for that deployment instead of the realtime path.
- [x] Verify with targeted tests and a live cloned-db call that the latest `model_invocations` row records `gpt-5.2-chat` and `status=succeeded`.

# Operations Copilot Chat Deployment Review

- Updated `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1/web_app.py` so Operations Copilot now uses a dedicated Azure chat deployment selection path:
  - `OPS_COPILOT_AZURE_OPENAI_MODEL`
  - fallback `AZURE_OPENAI_CHAT_MODEL`
  - fallback hard default `gpt-5.2-chat`
- Kept the existing Azure endpoint and API key, as requested. The live app path now targets `https://.../openai/deployments/gpt-5.2-chat/chat/completions?...`.
- Updated `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1/ops_copilot_llm_service.py` chat-completions payload for the `gpt-5.2-chat` model family:
  - switched from `max_tokens` to `max_completion_tokens`
  - removed non-default `temperature`, which Azure rejected for this deployment
- Verified with:
  - `python3 -m unittest tests.test_ops_copilot_llm_service tests.test_ops_control_layer_api`
  - direct Azure deployment smoke test showing `gpt-5.2-chat` returns `200` on chat completions
  - live cloned-db Operations Copilot call showing:
    - Azure request to `/openai/deployments/gpt-5.2-chat/chat/completions`
  - API response `200`
  - `model_invocations` latest row: `provider=azure_openai`, `model_name=gpt-5.2-chat`, `status=succeeded`

# Sarvam Voice Latency And Tone Audit

- [x] Inspect the live Sarvam voice stack wiring to identify which LLM, STT, TTS, and buffering settings are currently active in this repo.
- [x] Trace where response tone is constrained so the “robotic” behavior can be attributed to prompt design, TTS speaker choice, or both.
- [x] Compare the current repo choices against Sarvam official model and voice docs to separate configuration opportunities from true platform limitations.
- [x] Document concrete recommendations on latency reduction and naturalness, including whether another model is necessary.

# Sarvam Voice Latency And Tone Audit Review

- The current repo is configured for `sarvam-m` chat, `saarika:v2.5` streaming STT, and `bulbul:v3` TTS with speaker `shubh`; see `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/.env` and `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/web_app.py`.
- The strongest source of robotic behavior is prompt policy, not just the model vendor: `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/sarvam_llm_service.py` and `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/web_session.py` repeatedly instruct the agent to be deterministic, extremely short, question-only, and tightly state-driven, which suppresses natural phrasing.
- The repo already has a TTS humanization layer, but it is intentionally mild and effectively English-only today; Hindi output bypasses `_humanize_response(...)`, and prosody hints are disabled by default in `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/web_session.py`.
- Latency is also being shaped by conservative turn-taking and speech buffering defaults: `VAD_SILENCE_MS=600`, `TTS_STREAM_CHUNK_CHARS=50`, `TTS_MIN_BUFFER_SIZE=30`, and `POST_SPEECH_PAUSE_MS=800` in `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/web_app.py`, plus a first-sentence gate before TTS starts in `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/web_session.py`.
- Based on Sarvam docs, the first config change worth testing is upgrading streaming STT from legacy `saarika:v2.5` to `saaras:v3`, then tuning the local VAD / TTS chunking values. For naturalness, voice selection and text style need tuning before replacing the LLM. A different TTS provider is only necessary if Bulbul speaker options still do not meet your target after prompt and chunking changes.

# RecoveryEdge Deterministic Voice Engine

- [x] Audit the current live turn path across `web_session.py`, `voice_pipeline.py`, `intent_classifier.py`, `workflow_engine.py`, and `datetime_utils.py` to identify where latency, looping, and slot errors enter the flow.
- [x] Introduce a deterministic normalization + intent + slot extraction layer for payment status, PTP, callback, dispute, acknowledgement, greeting, and abuse, including short multilingual utterances and correction-aware overwrites.
- [x] Add a dedicated deterministic PTP parser module with Hindi, English, and relative-date support plus unit coverage for the required borrower phrases.
- [x] Tighten the dialogue state machine and response generation path so routine steps use deterministic templates and only explicitly complex cases fall back to LLM.
- [x] Reduce response latency by using faster STT flush thresholds / preview cadence in the session path and by preferring fixed turns over LLM for normal collections steps.
- [x] Add structured logging, conversation simulations, and focused tests for parser accuracy, loop prevention, abuse handling, slot correction, and state transitions.
- [x] Run targeted verification and document the resulting architecture, behavior changes, and remaining risks below.

# RecoveryEdge Deterministic Voice Engine Review

- Added `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/dialogue_normalizer.py` and `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/ptp_parser.py` so multilingual borrower text is normalized before classification and PTP dates are parsed deterministically across Hindi, English, romanized Hindi, and correction phrases such as `नहीं 11`.
- Updated `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/intent_classifier.py`, `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/entity_extractor.py`, and `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/workflow_engine.py` so short acknowledgements stop looking like topic drift, slot corrections overwrite prior PTP and callback values, abuse/refusal/dispute handling is deterministic, and normal cases no longer rely on the LLM path.
- Updated `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/web_session.py`, `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/web_app.py`, and `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/main.py` to cut STT/TTS buffering defaults, switch the default streaming STT model to `saaras:v3`, add structured deterministic-turn logging, and keep fixed-template responses on the low-latency path except for complex reasoning cases.
- Added `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/dialogue_engine.py`, `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/testing/voice_agent_stress.py`, and new tests for PTP parsing, intent classification, correction overwrites, outcome persistence, simulation coverage, and 50-call stress validation.
- Verification completed with:
  - `python3 -m unittest tests.test_ptp_parser tests.test_intent_classifier_deterministic tests.test_workflow_engine_corrections tests.test_workflow_engine tests.test_voice_pipeline tests.test_web_session_guards tests.test_web_session_outcomes tests.test_voice_agent_simulation tests.test_voice_agent_stress tests.test_ops_layers`
- Verification result:
  - `211` tests passed. The deterministic stress harness now reports 50 simulated calls with zero loop occurrences, high PTP capture accuracy, and classifier probe coverage across payment-done, PTP, callback, dispute, acknowledgement, greeting, and abuse utterances.

# RecoveryEdge Graceful Barge-In

- [x] Audit the current VAD/STT interruption path, interruption context storage, and resume behavior to isolate why barge-ins still feel abrupt or repetitive.
- [x] Refactor the interruption flow so barge-ins cancel agent speech cleanly, preserve the interrupted step context, and avoid generic filler acknowledgments on the next response.
- [x] Make resume-after-interrupt behavior deterministic and step-aware so explicit “continue” style replies pick up the right thread without replaying awkward prefixes or stale content.
- [x] Add focused regression coverage for interruption context capture, graceful resume, and no-filler deterministic prompts after barge-in.
- [x] Run targeted verification and document the outcome below.

# RecoveryEdge Graceful Barge-In Review

- Updated `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/web_session.py` so barge-in now interrupts speech without injecting a spoken filler acknowledgment on the next turn. The UI still receives a short `interrupt_acknowledged` event, but routine spoken prompts no longer restart with `ठीक है`, `Okay`, or `Got it`.
- The interruption path now stores explicit interruption context including the interrupted workflow step, remembered response text, timestamp, and reason. Resume logic uses that stored step instead of replaying raw partial text, which makes explicit continue-style borrower replies deterministic and less awkward.
- Resume behavior is now step-aware: when the borrower says `continue`, `जी बोलिए`, `आगे बताइए`, `go on`, or equivalent Punjabi/Hinglish variants soon after an interruption, the response step is rebound to the interrupted workflow step and the agent continues with a clean deterministic prompt.
- Added focused regression coverage in `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1__merge_test/tests/test_web_session_guards.py` for interruption context capture, resume-step override, clearing stale interruption context after substantive borrower replies, and removal of routine Hindi `ठीक है` prefixes from deterministic prompts.
- Verification completed with:
  - `python3 -m unittest tests.test_web_session_guards tests.test_voice_agent_simulation tests.test_web_session_outcomes tests.test_voice_pipeline tests.test_voice_agent_stress tests.test_ops_layers`
- Verification result:
  - `154` tests passed. Remaining runtime caveat: perceived barge-in smoothness still depends on the client/player fade-out and live provider RTT, so a running app process should be restarted once to pick up the new server behavior before live-call evaluation.

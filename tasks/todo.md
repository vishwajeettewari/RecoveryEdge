# Current Task

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

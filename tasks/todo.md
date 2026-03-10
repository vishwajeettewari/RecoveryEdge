# Current Task

- [x] Reproduce the PTP loop for ordinal-date commitments like `I will make the payment on 12th` and inspect the parsing/workflow path.
- [x] Implement the minimal fix so ordinal-date replies auto-capture PTP, acknowledge once, and persist the outcome data.
- [x] Add regression coverage for workflow/session persistence and verify the focused suite.

# Review

- Root cause: `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1/datetime_utils.py` did not parse ordinal day-of-month replies like `12th`, so `parse_date_from_text(...)` returned `None` and the workflow stayed on `ask_ptp_or_callback`, causing the agent to repeat the question.
- Fixed `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1/datetime_utils.py` to support:
  - ordinal day phrases such as `12th`
  - day-of-month phrases such as `12 तारीख`
  - future-month rollover when the mentioned day has already passed in the current month
- This fix feeds both the deterministic workflow engine and the live session parser, so the agent now auto-captures PTP for ordinal-date commitments instead of looping.
- Added regression coverage in `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1/tests/test_workflow_engine.py` for:
  - current-month ordinal capture
  - next-month rollover for past ordinal dates
- Added persistence-path coverage in `/Users/vishwajeet/AI_Collections_Agent_Sarvam_V1/tests/test_web_session_outcomes.py` proving that `handle_text("I will make the payment on 12th")`:
  - sets `ptp_date`
  - advances the workflow to `closing`
  - persists the PTP into backend outcome data
  - increments campaign PTP metrics
- Verification:
  - `python3 -m unittest tests.test_workflow_engine tests.test_web_session_outcomes`
  - `python3 -m unittest tests.test_workflow_engine tests.test_web_session_guards tests.test_web_session_outcomes`

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

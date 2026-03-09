# Current Task

- [x] Map each promised client-demo capability to the relevant backend, frontend, and test surfaces.
- [x] Audit and verify upload, campaign creation, calling, metric persistence, dashboard refresh, discipline variables, and operations copilot flows.
- [x] Document demo blockers, weak spots, and verification results with concrete file references.

# Review

- Verified the main backend and frontend surfaces with `python3 -m unittest tests.test_portfolio_wizard tests.test_ops_layers tests.test_v2_platform_api tests.test_ops_control_layer_api tests.test_web_session_outcomes tests.test_actions tests.test_auth_rbac_api` and `npm test -- --run`.
- Confirmed the strongest proof path is API-driven and green, but several demo gaps remain in the live UX path: outbound telephony depends on Twilio/Sarvam/public `wss://` setup, the calling console’s manual commitment save path updates SQLite but not the Excel sink, and the dashboards do not auto-refresh after calls.
- Confirmed risk metrics like cure rate and roll-forward are not produced by a single call alone; the current end-to-end proof manually seeds DPD snapshots to light up those portfolio movement views.

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

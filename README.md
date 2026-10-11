# Faceless Science — visuals-first Gemini Shorts

## Current recommended workflow (moving footage)

**Use [Real Motion Footage Preview](https://github.com/ahmedelgaml70/faceless/actions/workflows/motion-preview.yml), not the legacy photo slideshow generator.** The experimental motion workflow has passed end-to-end tests with five genuine Wikimedia video clips, Gemini-matched narration, corrected compact subtitles, and a successful technical QA result. It is manual-only and never uploads to YouTube.

The most recent output still has a quality limitation: Commons videos tend to be landscape-oriented, which requires reframing for vertical Shorts. To obtain **native portrait, full-screen stock footage at no API charge**, add a free Pexels API key as the GitHub Actions secret PEXELS_API_KEY. The source picker explicitly requests portrait video from Pexels and preserves attribution. Even with portrait footage, human editorial review is required before publishing.


**Version 5: photo-grounded storytelling.** This project automatically creates faceless educational Shorts on GitHub Actions using Gemini, authentic Wikimedia Commons photography, Kokoro narration and FFmpeg. It does **not** draw SVGs, graphics, cartoons, diagrams, or generate AI substitute images.

## Why the new pipeline is different

The former system **wrote a script first** and struggled to find photography for claims such as "shock wave expands like a balloon." That produced irrelevant stock visuals or a failed job.

The new system does the reverse, and shortens the video rather than adding unrelated filler when fewer authentic photos are available:

1. Pick a camera-filmable science topic from `topics.txt` (or the manually entered workflow topic).
2. Search public Commons image files in several *topic-specific* search groups.
3. Check the exact file's rights metadata: only Public Domain, CC0 and certain CC BY licenses are accepted; exclude unknown, ND, NC, SA and SVG/illustration media.
4. Use the Gemini API to **inspect the image pixels**; reject drawings, ads, mislabelled pictures and irrelevant results.
5. Reject near-duplicate photographs and require **at least four and up to six different approved photos**. If there aren't six, fail safely.
6. Tell Gemini what the four to six real shots depict, in a fixed order, and ask it to write exactly four to six connected scenes **for those shots** (roughly 70–125 narrated words).
7. Render Kokoro narration with PurffleShorts, then replace the base visuals with gentle photo pans/crops and **text-only lower-third subtitles**. No fake scientific overlays.
8. Reject videos that violate media licensing, photo/scene matching, portrait video format, audio, or storyboard-grounding requirements. Save MP4, source photos, scripts, QA report and photographer credits in the workflow artifact.

This approach values authenticity over output volume. It may fail if Commons or the Gemini Free tier cannot supply the required imagery.

## Run for $0 (within applicable free limits)

- Open [Generate Gemini Short](https://github.com/ahmedelgaml70/faceless/actions/workflows/generate-shorts.yml), then **Run workflow**. Start with a very visual topic such as **How a rainbow forms after rain**.
- Set the **GEMINI_API_KEY** Actions secret; the key stays private. The existing Gemini API project must be eligible for free API calls to maintain the $0 cost requirement. Do not add billing or upgrades just for this prototype.
- After a successful run, open **Artifacts → shorts-preview-N**, then review `short.mp4`, `script.json`, `visual_manifest.json`, `selection_report.json`, `quality_report.json`, and the sourced `media/*.jpg` photographs.
- Verify scientific claims, reuse permissions, context and how the final images appear before publishing.

The script is *AI-authored* and the image relevance check is *AI-assisted*. Neither guarantees scientific accuracy, copyright clearance, originality or viewer retention. The resulting media remains subject to manual review before any public publication.

## Operational controls

GitHub-hosted runners can execute without a running Mac, using public-repository GitHub Actions subject to platform policies. `schedule` is **disabled** for video generation. Video generation only runs when you explicitly start it. Video uploads are **OFF** by default. YouTube is never uploaded from CI/push validation runs; the optional manual-run upload step requires explicit `PRIVATE_UPLOAD_ENABLED=true`, a valid private `YOUTUBE_TOKEN_JSON` OAuth secret, a passing QA check, and always requests **Private** privacy. A Gemini API key does not authorize YouTube uploads.

For YouTube OAuth authorization, use a properly configured Google Cloud YouTube Data API OAuth Desktop client and `python -m purffle_shorts auth` on a trusted machine, then store only the resulting `token.json` as GitHub Actions secret `YOUTUBE_TOKEN_JSON`. Do **not** commit tokens or credentials to this public repository. Google OAuth Testing refresh tokens may expire.

**Security:** The third-party PurffleShorts renderer runs code from a commit pinned in the Actions workflow; review that code before granting it OAuth access. Official MediaWiki licenses are per-file; user-entered metadata can be wrong, so verify Commons description pages and any additional reuse conditions. Photographer attribution is appended to the YouTube description for CC BY photos.

## Project files

- `scripts/prepare_storyboard.py` — select six real licensed photos **before** writing the narration
- `scripts/prepare_content.py` — Commons API fetching, title checks, Gemini visual verification and safe photo cropping (shared helpers)
- `scripts/cinematic_post.py` — genuine-photo Ken Burns movement, short dissolves and lower-third captions
- `scripts/quality_check.py` — fail-closed technical and licensing metadata checks
- `topics.txt` — photography-friendly science topics
- `.github/workflows/generate-shorts.yml` — manual generation and disabled-by-default private upload
- `.github/workflows/validate.yml` — source-compilation and topic checks

Next milestone: inspect a successfully generated photo-grounded visual-first documentary, then source more authentic *moving camera footage* when rights-compatible clips are available. The pipeline is not a guarantee of YouTube monetization or a $3,000/month income.

## Experimental real moving-footage pipeline — V6

The photo slideshow is not good enough. A separate workflow now experiments with REAL camera footage:

- [Run Real Motion Footage Preview](https://github.com/ahmedelgaml70/faceless/actions/workflows/motion-preview.yml).
- scripts/prepare_motion.py searches licensed *video clips* (Wikimedia Commons by default and Pexels optionally), then uses Gemini to inspect real frames **before writing** a matching narration.
- scripts/edit_motion.py uses actual camera motion and hard footage cuts, keeps Kokoro narration, and overlays simple text subtitles.
- scripts/quality_motion.py rejects frozen footage, missing source credits, low-quality video, and missing narration.
- No SVG, artificial animation, diagrams, or fallback photo slideshows are permitted in this workflow.
- This is experimental, not the production default until the output has passed both the full run and a human visual review.

### Free source choices

Without another key, Wikimedia Commons provides a limited catalog of free video clips. A run may fail if it cannot find four genuinely suitable real moving clips. The source check permits Public Domain, CC0 and certain CC BY video files, excluding unknown, ShareAlike and noncommercial licensing metadata.

**Optional: Free Pexels video API.** Pexels provides a free API for actual stock videos. To enable broader stock coverage, obtain a Pexels API key at https://www.pexels.com/api/ and store it in GitHub repository Secrets as PEXELS_API_KEY. Do not share the key in chat or commit it. The workflow includes a prominent Pexels link and contributor credits in metadata. See Pexels license and API attribution requirements.

This experimental workflow does **not** upload to YouTube, even if upload-related variables exist. GitHub Actions usage and Gemini image inspection remain subject to their free-tier limits, while content quality and YouTube monetization are never guaranteed.

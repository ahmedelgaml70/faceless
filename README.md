# Faceless Science — visuals-first Gemini Shorts

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

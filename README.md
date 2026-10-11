# Faceless Science — Gemini Shorts automation

**Status:** GitHub Actions can render a video with your Gemini API key (first run passed). Version 4 removes ALL drawn diagrams, SVG/vector artwork, programmed animations and fake visual replacements. It uses real Wikimedia Commons photographs only, modest camera moves and text-only captions. Videos fail closed when enough relevant licensed photos cannot be found. **Version 4 still needs its first full render test.**

## Zero paid software, no local LLM

Pipeline: GitHub Actions → Gemini script + editorial rewrite → licensed Wikimedia Commons **photographs** → Kokoro narration → PurffleShorts audio base → photographic re-edit (gentle pan and zoom + text-only captions) → photo-only quality gate → downloadable preview.

No Ollama, paid video platform, cloud hosting subscription, or Mac computer required. Standard hosted GitHub runners for **public repositories** are free under GitHub Actions terms. Confirm your Gemini account is on an eligible **Free** tier, and keep spending caps at $0. Free software does not mean guaranteed YouTube earnings.

## Run it

1. In repository **Settings → Secrets and variables → Actions → Secrets**, save your Gemini key as **GEMINI_API_KEY**.
2. Open **Actions → Generate Gemini Short → Run workflow**. Optionally supply a specific science topic.
3. After completion, download **shorts-preview-N** from the run's Artifacts section. It includes the MP4, script, scene licensing manifest, visual style report, attribution in the description metadata, and the QA report.
4. Check video, audio, visual suitability, citations, factual claims and originality before publication. **A passing automatic check does not constitute human/editorial approval.**

If Commons is inaccessible or produces fewer than **3 distinct suitable licensed photographs** and at least 2 directly matched scenes, the workflow will **fail closed** and never upload a fallback drawing. Change the topic and run again; do not treat an automatic video as cleared for publication.

### Automatic daily generation

The `schedule` event in `.github/workflows/generate-shorts.yml` remains commented out. Enable it only after repeated manually inspected outputs succeed. Scheduled jobs may be delayed or skipped. All generated videos remain previews unless you explicitly enable the separate private-upload setting.

### Default visuals and licenses

`scripts/prepare_content.py` uses Wikimedia's public MediaWiki API and downloads only metadata-identified Public Domain, CC0 or CC BY images. It excludes CC BY-SA, NC, ND, unknown and restricted licenses. It logs rights, author, and source page in `prepared/visual_manifest.json`. CC BY attribution is also added to the YouTube description. For unmatched scenes, the job fails rather than generating any illustration, SVG, diagram or misleading stock footage. Any claimed license and reuse eligibility should still be confirmed manually at the source page because Commons metadata is not a legal guarantee.

### QA

`scripts/quality_check.py` verifies the count and dimensions of scene assets; at least two Commons visuals; that the render used only the prepared local assets; one 720×1280 video track, an audio track, plausible Shorts length, nonblank imagery, attribution when required, correct branding, and matching script/scene counts. It writes `prepared/quality_report.json`. It does **not** validate scientific truth or guarantee viewer interest or YouTube monetization eligibility.

### Optional YouTube private uploads

**Off by default.** Your Gemini API key cannot authorize uploading to YouTube.

1. In Google Cloud, enable **YouTube Data API v3**, create an OAuth Desktop application, and download its client JSON. Do not commit it.
2. On a trusted machine, authorize once using PurffleShorts (`python -m purffle_shorts auth`). It writes a refreshable `token.json`. OAuth apps in Testing status often issue short-lived refresh tokens.
3. Store the entire `token.json` as Actions secret **YOUTUBE_TOKEN_JSON**. Never paste the token into source code or a public issue.
4. Add an Actions variable **PRIVATE_UPLOAD_ENABLED** with value `true`. The upload step will run **only after the quality gate passes**, and uploads use YouTube's **private** privacy setting.
5. Confirm the next test's video appears as Private in YouTube Studio. Disable the variable on any unexpected behavior.

**Security:** This repo remains public; don't place credentials in it. The third-party PurffleShorts source is pinned to `bab8d5f97b8452d72287b0ee3af3cb8cc1a23bc8`. It is installed in GitHub-hosted runners; you should review third-party code before granting it YouTube access.

## Relevant files

- `.github/workflows/generate-shorts.yml`: manual workflow and optional private upload
- `.github/workflows/validate.yml`: lightweight syntax and topic-rotation check
- `scripts/select_topic.py`: rotation of pre-selected factual topics
- `scripts/prepare_content.py`: Gemini + Wikimedia + custom diagram assets
- `scripts/cinematic_post.py`: **no drawn graphics**; real-photo camera movement and text-only captions
- `scripts/quality_check.py`: fail-closed post-render gate
- `topics.txt`: topic bank

**Next milestone:** compare the cinematic preview to the prior still-image slideshow, then iterate on narration, visuals, accuracy, and actual audience retention. Technical success alone is not evidence of good content.

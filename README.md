# Faceless Science — Gemini Shorts automation

**Status:** GitHub Actions can render a video with your Gemini API key (first run passed). Version 2 adds licensed visual sourcing, original diagrams, unique scene matching, clearer scripts, attribution, and a fail-closed quality gate. **The new version still needs its first live test.**

## Zero paid software, no local LLM

Pipeline: GitHub Actions → Gemini script + second-pass editorial review → Wikimedia Commons photo selection (Public Domain, CC0, and CC BY 2/3/4 only) → otherwise locally rendered original diagrams → Kokoro narration → FFmpeg render → independent technical/licence-metadata QA → GitHub artifact.

No Ollama, paid video platform, cloud hosting subscription, or Mac computer required. Standard hosted GitHub runners for **public repositories** are free under GitHub Actions terms. Confirm your Gemini account is on an eligible **Free** tier, and keep spending caps at $0. Free software does not mean guaranteed YouTube earnings.

## Run it

1. In repository **Settings → Secrets and variables → Actions → Secrets**, save your Gemini key as **GEMINI_API_KEY**.
2. Open **Actions → Generate Gemini Short → Run workflow**. Optionally supply a specific science topic.
3. After completion, download **shorts-preview-N** from the run's Artifacts section. It includes the MP4, script, scene licensing manifest, attribution in the description metadata, and the QA report.
4. Check video, audio, visual suitability, citations, factual claims and originality before publication. **A passing automatic check does not constitute human/editorial approval.**

If Commons is inaccessible or produces fewer than **2 usable licensed visuals** for the topic, the workflow will **fail closed**, saving diagnostics rather than uploading a generic all-gradient video. Change the topic and run again; do not treat an automatic video as cleared for publication.

### Automatic daily generation

The `schedule` event in `.github/workflows/generate-shorts.yml` remains commented out. Enable it only after repeated manually inspected outputs succeed. Scheduled jobs may be delayed or skipped. All generated videos remain previews unless you explicitly enable the separate private-upload setting.

### Default visuals and licenses

`scripts/prepare_content.py` uses Wikimedia's public MediaWiki API and downloads only metadata-identified Public Domain, CC0 or CC BY images. It excludes CC BY-SA, NC, ND, unknown and restricted licenses. It logs rights, author, and source page in `prepared/visual_manifest.json`. CC BY attribution is also added to the YouTube description. For unmatched scenes, it creates simple original labelled diagrams instead of stock images. Any claimed license and reuse eligibility should still be confirmed manually at the source page because Commons metadata is not a legal guarantee.

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
- `scripts/quality_check.py`: fail-closed post-render gate
- `topics.txt`: topic bank

**Next milestone:** successfully run the updated workflow, inspect its generated MP4 and licensing manifest, and adjust any genuine API or quality failures.

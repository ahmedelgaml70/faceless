# Faceless — Gemini Shorts Automation

A **$0-software-cost prototype** for generating one AI-assisted YouTube Short on GitHub Actions. No local language model or continuously running laptop required.

## What happens

GitHub Actions → topic selection → Gemini API script → Kokoro voiceover → FFmpeg video/captions → downloadable GitHub Actions artifact.

**Status:** video generation is configured for manual testing first. YouTube uploads are **OFF** by default and must be separately authorized using OAuth credentials. No videos publish publicly from this repository.

## Quick start

1. Go to **Settings → Secrets and variables → Actions → Secrets → New repository secret**.
2. Create secret **GEMINI_API_KEY** (use the key you already have; never commit or share it).
3. Make sure your Gemini project is using its **Free tier**. GitHub Actions is free for public repositories with standard hosted runners, subject to GitHub usage policies; if you make this private, confirm remaining included minutes and your spending limit.
4. Go to **Actions → Generate Gemini Short → Run workflow**. Enter a topic, or leave it blank for an automatic suggestion from `topics.txt`.
5. Open that workflow run → **Artifacts** → download `shorts-preview-...` after it finishes.
6. Review the video, its claims, visuals, and audio before doing any public publishing.

The workflow uses the open-source [PurffleShorts](https://github.com/Chamanrajragu/purffle-shorts) rendering engine **pinned to commit `bab8d5f97b8452d72287b0ee3af3cb8cc1a23bc8`**. This runs third-party code in a GitHub Actions runner. It has not been independently end-to-end tested with your credentials.

## Gemini and optional image sourcing

The default Gemini model is `gemini-3.5-flash-lite`, which Google advertises with a free API tier subject to availability and quota. Change it via repository **Actions variable** `GEMINI_MODEL` if needed.

Without stock media, local/procedural backgrounds may look basic. You can optionally add a free Pixabay API key as the **PIXABAY_API_KEY** secret to request stock visuals subject to Pixabay terms, rates, and availability.

Never rely on AI scripts without fact-checking. This is a technical video-generation experiment, **not a guaranteed monetization system**.

## Automatic scheduling

For safety, automatic daily runs are **disabled until the first manual test succeeds**. When ready, enable the commented `schedule` event in `.github/workflows/generate-shorts.yml`. GitHub scheduled workflows may run late or be dropped. Keep to a low initial output frequency.

## Future private YouTube upload setup

Uploading requires a separate **Google OAuth Desktop client** for YouTube Data API v3 (a Gemini API key does not authorize uploads).

1. Set up YouTube Data API v3 and OAuth Desktop client on Google Cloud Console.
2. Authorize YouTube **locally once** with PurffleShorts using `python -m purffle_shorts auth` and your downloaded `credentials.json`. It creates a `token.json` containing a refresh token. A token from an OAuth app in Testing mode can expire quickly.
3. Store the full `token.json` as an Actions secret named **YOUTUBE_TOKEN_JSON**. Never upload `credentials.json`, `token.json`, or API keys to your repository.
4. Create an Actions **variable** named `PRIVATE_UPLOAD_ENABLED` with value `true`.
5. Re-run manually and confirm that the video appears **Private** in YouTube Studio.
6. If upload fails, set `PRIVATE_UPLOAD_ENABLED` back to `false`.

The workflow explicitly requests **private**, never public, uploads. The pipeline alone cannot guarantee YouTube monetization, copyright clearance, or factual accuracy. Creator monetization reviews disallow repetitive low-value content.

## Operational details

- `permissions: contents: read` for minimal GitHub access.
- No credentials are committed to the repository.
- Rendering uses a temporary hosted Linux runner; it does not persist the videos except as workflow artifacts.
- Runner/install time and third-party API quotas may limit use.
- Keep a tight Actions budget on any billable GitHub plan and confirm Gemini Free-tier status to maintain a true $0 plan.

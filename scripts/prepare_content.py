#!/usr/bin/env python3
"""Prepare a Gemini script and scene-specific visual assets before rendering.

Only Wikimedia Commons images marked Public Domain, CC0 or CC BY (2/3/4) are
downloaded. Attribution is added to the YouTube description for CC BY assets.
Technical checks do NOT replace human copyright/factual review.
"""
from __future__ import annotations

import html
from html.parser import HTMLParser
import json
import logging
import os
from pathlib import Path
from urllib.parse import urlparse
import re
import sys
import time

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, UnidentifiedImageError
from io import BytesIO

# Script runs with engine/ as cwd. PurffleShorts is already installed.
from purffle_shorts.config import Settings
from purffle_shorts.llm import LLM
from purffle_shorts.script import write_script, review_script

LOG = logging.getLogger("faceless")
HERE = Path.cwd()
PREPARED = HERE / "prepared"
MEDIA = HERE / "media"
COMMONS = "https://commons.wikimedia.org/w/api.php"
HEADERS = {
    "User-Agent": "FacelessScienceBot/0.3 (https://github.com/ahmedelgaml70/faceless)",
    "Accept": "application/json",
}
MAX_SCENES = 11
MIN_COMMONS = 2
STOPWORDS = {"the", "with", "from", "that", "this", "what", "into", "through", "under", "over", "near", "dark", "slow", "motion", "giant", "close", "extreme", "high", "stock", "film", "video", "photo", "visual", "surface"}


class HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.words: list[str] = []

    def handle_data(self, data: str) -> None:
        self.words.append(data)


def clean_html(raw: str) -> str:
    stripper = HTMLStripper()
    stripper.feed(html.unescape(raw or ""))
    return " ".join(" ".join(stripper.words).split())[:180]


def permitted(meta: dict) -> tuple[str, str] | None:
    license_name = clean_html(meta.get("LicenseShortName", {}).get("value", ""))
    license_url = meta.get("LicenseUrl", {}).get("value", "")
    name = license_name.casefold().replace(" ", "").replace("-", "")
    if "cc0" in name or name in ("publicdomain", "pd", "pdold", "pduse"):
        return license_name or "Public domain", license_url
    if name in ("ccby2.0", "ccby3.0", "ccby4.0") and "creativecommons.org/licenses/by/" in license_url:
        return license_name, license_url
    return None


def word_stems(text: str) -> set[str]:
    out = set()
    for raw in re.findall(r"[a-z]{3,}", text.casefold()):
        if raw in STOPWORDS:
            continue
        token = raw
        if token.endswith("ing") and len(token) > 5:
            token = token[:-3]
            if token.endswith("k"):
                token += "e"
        elif token.endswith("es") and len(token) > 5:
            token = token[:-2]
        elif token.endswith("s") and len(token) > 4:
            token = token[:-1]
        out.add(token)
    return out


def relevant_title(query: str, title: str) -> tuple[bool, int]:
    """Require literal topic overlap; avoid matching one ambiguous term such as 'jet'."""
    q = word_stems(query)
    t = word_stems(title.replace("File:", ""))
    overlap = len(q & t)
    return overlap >= (2 if len(q) >= 2 else 1), overlap


def find_candidates(query: str) -> list[dict]:
    params = {
        "action": "query", "generator": "search", "gsrsearch": query[:90],
        "gsrnamespace": 6, "gsrlimit": 12, "prop": "imageinfo",
        "iiprop": "url|size|mime|extmetadata", "iiurlwidth": 1280,
        "format": "json", "formatversion": 2,
    }
    response = requests.get(COMMONS, params=params, headers=HEADERS, timeout=12)
    response.raise_for_status()
    results = response.json().get("query", {}).get("pages", [])
    valid = []
    for item in results:
        title = item.get("title", "")
        if any(w in title.lower() for w in ("logo", "trademark", "flag of", "icon of")):
            continue
        ii = (item.get("imageinfo") or [{}])[0]
        if ii.get("mime") not in ("image/jpeg", "image/png", "image/webp"):
            continue
        rights = permitted(ii.get("extmetadata") or {})
        if not rights:
            continue
        meta = ii.get("extmetadata", {})
        artist = clean_html(meta.get("Artist", {}).get("value", "")) or "Unknown contributor"
        if "by" in rights[0].casefold() and artist == "Unknown contributor":
            continue
        valid.append({
            "title": title, "artist": artist, "license": rights[0],
            "license_url": rights[1],
            "page": ii.get("descriptionurl", ""),
            "image_url": ii.get("thumburl") or ii.get("url", ""),
        })
    return valid


def get_image(src: dict) -> Image.Image:
    url = src["image_url"]
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ("upload.wikimedia.org", "commons.wikimedia.org"):
        raise ValueError("Refusing external media host")
    r = requests.get(url, headers={**HEADERS, "Accept": "image/*"}, timeout=18)
    r.raise_for_status()
    if len(r.content) > 12_000_000 or not r.headers.get("Content-Type", "").startswith("image/"):
        raise ValueError("Unexpected media content")
    with Image.open(BytesIO(r.content)) as im:
        if im.width < 280 or im.height < 260:
            raise ValueError("Image is too small")
        return ImageOps.exif_transpose(im).convert("RGB")


def font(size: int, bold: bool = False):
    path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    return ImageFont.truetype(path, size)


def linebreak(s: str, n: int = 27) -> list[str]:
    out, line = [], ""
    for word in s.split():
        if line and len(line + " " + word) > n:
            out.append(line)
            line = word
        else:
            line = (line + " " + word).strip()
    if line:
        out.append(line)
    return out[:4]


def compose_photo(photo: Image.Image, query: str, idx: int) -> Image.Image:
    w, h = 720, 1280
    # Blurred duplicate fills the portrait canvas without unnatural cropping.
    bg = ImageOps.fit(photo, (w, h), method=Image.Resampling.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(30)).convert("RGB")
    bg = Image.blend(bg, Image.new("RGB", (w, h), "#071626"), 0.56)
    d = ImageDraw.Draw(bg)
    d.rounded_rectangle((16, 110, 704, 1180), radius=28, fill="#0b1929")
    body = ImageOps.contain(photo, (684, 1040), method=Image.Resampling.LANCZOS)
    bg.paste(body, ((w - body.width) // 2, (h - body.height) // 2))
    d = ImageDraw.Draw(bg)
    d.rounded_rectangle((16, 110, 704, 1180), radius=28, outline="#2e678d", width=3)
    return bg


def original_diagram(query: str, idx: int) -> Image.Image:
    """Fallback is an explicitly original labelled illustration, not stock."""
    w, h = 720, 1280
    im = Image.new("RGB", (w, h), "#071421")
    d = ImageDraw.Draw(im)
    for j in range(0, h, 6):
        red = 8 + j // 85
        d.rectangle((0, j, w, j + 5), fill=(red, 21 + j//95, 41 + j//55))
    d.ellipse((115, 245, 605, 735), outline="#4690c2", width=7)
    q = query.lower()
    if any(k in q for k in ("lightning", "electric", "thunder", "power")):
        d.line([(385, 245), (285, 480), (407, 468), (250, 748), (304, 540), (220, 550)], fill="#f4d873", width=24, joint="curve")
        for radius in (130, 210, 290):
            d.arc((365-radius, 498-radius, 365+radius, 498+radius), 20, 165, fill="#55c4f0", width=5)
    elif any(k in q for k in ("space", "planet", "moon", "sun", "star", "earth", "orbit")):
        d.ellipse((213, 350, 507, 640), fill="#245d9c", outline="#86d4f7", width=7)
        d.arc((90, 390, 625, 660), 40, 322, fill="#efb95a", width=10)
        d.ellipse((554, 391, 613, 450), fill="#ffdf97")
        for x, y in ((90,260),(590,307),(140,760),(554,785),(304,205)):
            d.ellipse((x,y,x+7,y+7), fill="#dbeafd")
    elif any(k in q for k in ("jet", "plane", "aircraft", "speed", "supersonic")):
        d.polygon([(105, 540), (575, 510), (595, 540), (575, 568), (105, 540)], fill="#a8d0eb")
        d.polygon([(325, 535), (180, 725), (465, 548)], fill="#388ab8")
        for a in (90, 140, 190):
            d.arc((350-a, 540-a, 350+a, 540+a), 220, 320, fill="#c4f1ff", width=5)
    elif any(k in q for k in ("cloud", "storm", "sky", "weather")):
        for x,y,r in ((250,440,105),(360,380,140),(490,450,110)):
            d.ellipse((x-r,y-r,x+r,y+r),fill="#416f92")
        for x in (240,340,445):
            d.line([(x,650),(x-45,750)],fill="#6fbddd",width=7)
    elif any(k in q for k in ("heat", "hot", "air", "temperature")):
        for x in (235,335,435,535):
            d.arc((x-45,360,x+45,730),60,275,fill="#f6b566",width=9)
    elif any(k in q for k in ("ocean", "water", "sound", "wave", "sea")):
        for off in (0, 75, 150, 225):
            pts = [(x, int(465 + off + 36*__import__("math").sin((x+off)/55))) for x in range(75, 645, 5)]
            d.line(pts, fill="#5ec8ef", width=9, joint="curve")
    else:
        for a,b,c in ((173,345,55),(425,410,78),(318,653,45)):
            d.ellipse((a-c,b-c,a+c,b+c), fill="#2d82bb", outline="#9cdbfb", width=6)
        d.line([(173,345),(425,410),(318,653),(173,345)], fill="#d8ad69", width=10)
    # Leave the frame free of labels: the video renderer overlays timed captions.
    d.line((55, 1035, 665, 1035), fill="#245479", width=4)
    return im


def choose_visual(query: str, topic: str, used: set[str]) -> tuple[Image.Image, dict]:
    options = []
    for phrase in (query, " ".join(query.split()[:2]), topic):
        if phrase and phrase not in options:
            options.append(phrase)
    for phrase in options:
        try:
            candidates = find_candidates(phrase)
        except (requests.RequestException, ValueError) as exc:
            LOG.warning("Commons search unavailable (%s): %s", phrase, str(exc)[:100])
            continue
        for src in candidates:
            good, overlap = relevant_title(query, src["title"])
            if not good:
                continue
            src["title_overlap_terms"] = overlap
            if src["page"] in used:
                continue
            try:
                img = get_image(src)
            except (requests.RequestException, ValueError, UnidentifiedImageError, OSError) as exc:
                LOG.warning("Commons image rejected: %s", str(exc)[:90])
                continue
            used.add(src["page"])
            return img, src
        time.sleep(0.3)
    return None, {}


def produce(topic: str) -> None:
    PREPARED.mkdir(exist_ok=True)
    MEDIA.mkdir(exist_ok=True)
    settings = Settings.from_env()
    settings.script_review = "rewrite"
    model = LLM(settings)
    verified_guidance = (
        "Editorial policy for educational video: use only established science. "
        "Avoid dramatic but misleading temperature, speed and scale comparisons. "
        "State units for numerical claims and identify exactly what is compared "
        "(e.g. lightning channel versus Sun surface, not the entire Sun). "
        "Say approximately when values vary. Never invent research studies, "
        "dates, statistics or quotations. Keep each scene concrete, visually filmable, "
        "and aligned with its search query; never invent footage. "
        "Prefer surprising explanations over empty subscribe prompts."
    )
    script = write_script(model, topic, settings, style="explainer", context=verified_guidance)
    script = review_script(model, script, settings)
    if "thunder" in topic.casefold() or "lightning" in topic.casefold():
        script.hook_text = "WHY THUNDER BOOMS"
    else:
        hook = script.hook_text.split()[:5]
        while hook and hook[-1].casefold() in {"the", "and", "or", "a", "an", "of", "to", "its", "it", "that"}:
            hook.pop()
        script.hook_text = " ".join(hook) or "HERE IS HOW IT WORKS"
    if len(script.scenes) >= 6 and re.match(r"^(drop a comment|follow for|subscribe|comment your|what is your)",
                                               script.scenes[-1].narration.strip(), flags=re.I):
        LOG.info("Removing generic end-of-video call to action")
        script.scenes.pop()
    if not 5 <= len(script.scenes) <= MAX_SCENES:
        raise RuntimeError(f"Scene count failed: {len(script.scenes)} (required 5-11)")
    if script.score is not None and script.score < 55:
        raise RuntimeError(f"Script's provisional editorial score too low: {script.score}")

    used: set[str] = set()
    manifest: list[dict] = []
    credits: list[str] = []
    for idx, scene in enumerate(script.scenes):
        original_query = scene.search_query
        photo, source = choose_visual(original_query, topic, used)
        if photo is not None:
            img = compose_photo(photo, original_query, idx)
            kind = "wikimedia-commons"
            if "by" in source["license"].casefold():
                credits.append(
                    f'Visual: {source["artist"]}, {source["title"]}, '
                    f'{source["license"]} ({source["license_url"]}), {source["page"]}'
                )
        else:
            img = original_diagram(original_query, idx)
            kind = "original-diagram"
        # Unique alphabetic token lets Purffle's existing local matcher map each
        # scene to exactly one asset; no scene ever silently uses a gradient.
        token = f"facelessscene{chr(ord('a') + idx)}"
        path = MEDIA / f"{token}_art.jpg"
        img.save(path, format="JPEG", quality=88, optimize=True)
        manifest.append({
            "index": idx, "query": original_query, "asset": str(path),
            "kind": kind, "source": source,
        })
        scene.search_query = token
        print(f"Scene {idx+1}/{len(script.scenes)}: {kind} for '{original_query}'", flush=True)

    if credits:
        script.description += "\n\nVisual source attributions:\n" + "\n".join(dict.fromkeys(credits))
    (PREPARED / "script.json").write_text(json.dumps(script.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    (PREPARED / "visual_manifest.json").write_text(
        json.dumps({"topic": topic, "scenes": manifest, "commons_count":
                    sum(x["kind"] == "wikimedia-commons" for x in manifest)},
                   indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"PREPARED: {len(manifest)} scene assets; Commons licensed: "
          f"{sum(x['kind']=='wikimedia-commons' for x in manifest)}", flush=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    topic = " ".join(sys.argv[1:]).strip()
    if not topic:
        raise SystemExit("Usage: prepare_content.py <topic>")
    produce(topic)

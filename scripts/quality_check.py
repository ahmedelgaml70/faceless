#!/usr/bin/env python3
"""Fail-closed quality gate for generated videos; never claims factual clearance."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from PIL import Image, ImageStat


def check() -> None:
    base = Path("prepared")
    plan = json.loads((base / "visual_manifest.json").read_text(encoding="utf-8"))
    script = json.loads((base / "script.json").read_text(encoding="utf-8"))
    scenes = plan["scenes"]
    failures = []
    commons = sum(x["kind"] == "wikimedia-commons" for x in scenes)
    if commons < 2:
        failures.append(f"Only {commons} Commons images; require at least 2 genuinely sourced visuals")
    if len(scenes) != len(script.get("scenes", [])):
        failures.append("Mismatch between visuals and script scene counts")
    for scene in scenes:
        if scene["kind"] == "wikimedia-commons":
            if int(scene.get("source", {}).get("title_overlap_terms", 0)) < 2:
                failures.append(f"Commons image lacks sufficient topic overlap: {scene['query']}")
        p = Path(scene["asset"])
        if not p.is_file() or p.stat().st_size < 12_000:
            failures.append(f"Missing or tiny visual: {p}")
            continue
        with Image.open(p) as image:
            if image.size != (720, 1280):
                failures.append(f"Wrong visual size: {p}")
            extrema = ImageStat.Stat(image.resize((80, 140))).stddev
            if max(extrema) < 8:
                failures.append(f"Scene is nearly blank: {p}")

    if not script.get("title") or len(script.get("scenes", [])) < 5:
        failures.append("Script is too short or missing title")
    if "PurffleStudios" in script.get("description", ""):
        failures.append("Default branding found in description")

    videos = sorted(Path("output_videos").glob("*/short.mp4"))
    if len(videos) != 1:
        failures.append(f"Expected one MP4, found {len(videos)}")
    video = videos[0] if videos else None
    if video:
        folder = video.parent
        metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
        if "PurffleStudios" in json.dumps(metadata):
            failures.append("Default branding in metadata")
        sources = metadata.get("visuals", [])
        if len(sources) != len(scenes):
            failures.append("Rendered scene count does not equal plan")
        if any(m.get("source") == "generated" for m in sources):
            failures.append("Renderer silently used a gradient scene")
        if any(m.get("source") != "local" for m in sources):
            failures.append("Unexpected media source in render")
        if not all((folder / name).is_file() for name in ("captions.srt", "script.json", "cover.jpg")):
            failures.append("Video output missing a required sidecar")
        if video.stat().st_size < 180_000:
            failures.append("Rendered MP4 unexpectedly small")

        cmd = ["ffprobe", "-v", "error", "-show_entries",
               "stream=codec_type,width,height:format=duration",
               "-of", "json", str(video)]
        p = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=30)
        probe = json.loads(p.stdout)
        streams = probe.get("streams", [])
        vids = [x for x in streams if x.get("codec_type") == "video"]
        auds = [x for x in streams if x.get("codec_type") == "audio"]
        if len(vids) != 1 or (vids[0].get("width"), vids[0].get("height")) != (720, 1280):
            failures.append("Video must contain one 720x1280 stream")
        if not auds:
            failures.append("No audio track")
        duration = float(probe.get("format", {}).get("duration", 0))
        if not 18 <= duration <= 65:
            failures.append(f"Video duration out of bounds: {duration:.1f}s")
        if any(s["kind"] == "wikimedia-commons" and "by" in s["source"]["license"].lower()
               for s in scenes) and "Visual source attributions" not in metadata.get("description", ""):
            failures.append("Required attribution missing from YouTube description")
    else:
        metadata = {}

    cinematic = Path("prepared/cinematic_report.json")
    if not cinematic.is_file():
        failures.append("Missing cinematic motion-render report")
    else:
        production = json.loads(cinematic.read_text(encoding="utf-8"))
        if production.get("version") != "cinematic-1":
            failures.append("Unexpected cinematic production version")
        if len(production.get("scene_types", [])) != len(scenes):
            failures.append("Cinematic scene types do not match scripted scenes")
        if video and abs(float(production.get("duration", 0)) - float(metadata.get("duration", 0))) > 1.2:
            failures.append("Cinematic report and source metadata duration disagree")

    report = {
        "status": "PASS" if not failures else "FAIL",
        "checks_are_not_fact_checking": True,
        "commons_assets": commons,
        "original_diagrams": len(scenes) - commons,
        "scene_count": len(scenes),
        "video": str(video) if video else None,
        "issues": failures,
        "note": "Technical/license-metadata checks are not a guarantee of factual accuracy, "
                "commercial suitability, or human approval.",
    }
    (base / "quality_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if failures:
        raise SystemExit("QUALITY GATE FAILED — do not upload")


if __name__ == "__main__":
    check()

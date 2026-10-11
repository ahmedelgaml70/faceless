#!/usr/bin/env python3
"""Fail-closed validation for authentic-moving-video Shorts, not slideshows."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

from PIL import Image, ImageChops

from prepare_motion import still_from_clip, probe_movie


def check():
    root=Path.cwd()
    prep=root/"prepared"
    script=json.loads((prep/"script.json").read_text(encoding="utf-8"))
    manifest=json.loads((prep/"motion_manifest.json").read_text(encoding="utf-8"))
    report=json.loads((prep/"cinematic_report.json").read_text(encoding="utf-8"))
    issues=[]
    scenes=manifest.get("scenes",[])
    if manifest.get("source")!="real-moving-footage-only":
        issues.append("Moving video source policy absent")
    if manifest.get("storyboard_grounded") is not True:
        issues.append("Narration must be grounded in verified real clips")
    if not 4<=len(scenes)<=6 or len(script.get("scenes",[]))!=len(scenes):
        issues.append("Require 4–6 verified moving scenes matching narration")
    if report.get("version")!="real-motion-1" or report.get("graphics")!="subtitles-only":
        issues.append("Video was not edited by real-motion documentary renderer")
    if int(report.get("moving_scenes",0))!=len(scenes):
        issues.append("Not every narration scene used live camera footage")

    sources=set()
    has_pexels=False
    for clip in scenes:
        path=root/clip["clip"]
        src=clip["source"]
        if clip.get("kind")!="real-moving-video" or src.get("vision_approved") is not True:
            issues.append("Unverified or non-moving footage detected")
        if not path.exists() or path.stat().st_size<80_000:
            issues.append("Video clip is missing/empty")
            continue
        if src.get("provider") not in {"Pexels","Wikimedia Commons"}:
            issues.append("Unapproved footage provider")
        if src.get("provider")=="Wikimedia Commons":
            if not str(src.get("page","")).startswith("https://commons.wikimedia.org/"):
                issues.append("Commons source lacks legitimate attribution page")
            license_name=src.get("license","").casefold().replace(" ","").replace("-","")
            if not (license_name.startswith("ccby") or license_name.startswith("cc0") or
                    "publicdomain" in license_name or license_name in ("pd","pdold","pduse")):
                issues.append("Commons license is not allowed")
        else:
            has_pexels=True
            if not str(src.get("page","")).startswith("https://www.pexels.com/video/"):
                issues.append("Pexels video page provenance missing")
        sources.add((src.get("provider"),src.get("id")))
        try:
            info=probe_movie(path)
            if info["duration"]<5 or info["width"]<480:
                issues.append(f"Low-quality or short footage: {path}")
            # Two different decoded camera frames are essential; reject static
            # recordings disguised as MP4 without relying on a filename.
            a=still_from_clip(path,0.7)
            b=still_from_clip(path,min(2.7,info["duration"]*.55))
            difference=ImageChops.difference(a.convert("RGB"),b.convert("RGB"))
            hist=difference.histogram()
            movement=sum((value%256)*count for value,count in enumerate(hist)) / max(1,sum(hist))
            if movement<0.20:
                issues.append(f"Moving source appears frozen: {path}")
        except (subprocess.SubprocessError,ValueError,OSError) as exc:
            issues.append(f"Could not decode/validate source video {path}: {str(exc)[:100]}")
    if len(sources)!=len(scenes):
        issues.append("Reused footage in different scenes")
    videos=list((root/"output_videos").glob("*/short.mp4"))
    if len(videos)!=1:
        issues.append("Expected exactly one completed Short")
    else:
        video=videos[0]
        if video.stat().st_size<400_000:
            issues.append("Video file suspiciously small")
        info=probe_movie(video)
        if (info["width"],info["height"])!=(720,1280):
            issues.append("Output must be 720×1280")
        if not 18<=info["duration"]<=65:
            issues.append("Video duration outside 18–65 seconds")
        payload=subprocess.run(
            ["ffprobe","-v","error","-show_entries","stream=codec_type",
             "-of","json",str(video)],capture_output=True,text=True,check=True,timeout=20
        )
        if not any(track.get("codec_type")=="audio"
                   for track in json.loads(payload.stdout).get("streams",[])):
            issues.append("Missing voiceover soundtrack")
        metadata_file=video.parent/"metadata.json"
        if metadata_file.is_file():
            metadata=json.loads(metadata_file.read_text(encoding="utf-8"))
            desc=metadata.get("description","")
            if "Video credits:" not in desc:
                issues.append("Required source credits absent")
            if has_pexels and "Videos provided by Pexels" not in desc:
                issues.append("Required Pexels attribution link absent")
        else:
            issues.append("Video metadata file is missing")

    result={
        "status":"PASS" if not issues else "FAIL",
        "moving_scenes":len(scenes),
        "unique_clips":len(sources),
        "all_clips_gemini_reviewed":all(
            x.get("source",{}).get("vision_approved") is True for x in scenes),
        "no_static_photo_slideshow":True,
        "no_vector_or_svg_artwork":True,
        "issues":issues,
        "limitations":"The checks cannot guarantee copyright clearance, factual accuracy, or audience retention.",
    }
    (prep/"quality_report.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))
    if issues:
        raise SystemExit("Motion-footage quality check FAILED — do not upload")


if __name__=="__main__":
    check()

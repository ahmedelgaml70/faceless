#!/usr/bin/env python3
"""Fail-closed production gate: authentic licensed photos, no SVG/drawn assets."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import subprocess

from PIL import Image


def check() -> None:
    root=Path("prepared")
    manifest=json.loads((root/"visual_manifest.json").read_text(encoding="utf-8"))
    script=json.loads((root/"script.json").read_text(encoding="utf-8"))
    scenes=manifest.get("scenes",[])
    failed=[]
    if manifest.get("visual_policy")!="licensed-real-photography-only":
        failed.append("Visual policy must require real photography")
    if len(scenes)!=len(script.get("scenes",[])):
        failed.append("Photo count must equal script scene count")
    sources=Counter()
    direct=0
    for scene in scenes:
        if scene.get("kind")!="wikimedia-photo":
            failed.append(f"Scene {scene.get('index')} uses non-photo or generated asset")
        source=scene.get("source",{})
        page=source.get("page","")
        if not page.startswith("https://commons.wikimedia.org/"):
            failed.append("Photo missing trusted Commons attribution page")
        if source.get("url","").lower().endswith(".svg"):
            failed.append("SVG imagery is forbidden")
        sources[page]+=1
        if sources[page]>2:
            failed.append("Single Commons photograph reused too often")
        if scene.get("match")=="direct":
            direct+=1
        if not source.get("license"):
            failed.append("Commons license missing")
        if int(source.get("title_overlap_terms",0))<1:
            failed.append("Photo has no verified title relevance")
        path=Path(scene.get("asset",""))
        if not path.is_file():
            failed.append(f"Missing photo {path}")
        else:
            with Image.open(path) as im:
                if im.size!=(720,1280):
                    failed.append(f"Photo dimensions incorrect: {path}")
                if im.format not in ("JPEG","PNG","WEBP"):
                    failed.append(f"Unexpected image format: {path}")
    if len(sources)<3:
        failed.append("Fewer than 3 distinct real licensed photographs")
    if direct<2:
        failed.append("Fewer than 2 scenes have directly matching licensed photography")

    videos=list(Path("output_videos").glob("*/short.mp4"))
    if len(videos)!=1:
        failed.append(f"Expected one rendered MP4; found {len(videos)}")
        video=None
    else:
        video=videos[0]
    meta={}
    if video:
        folder=video.parent
        for file in ("script.json","metadata.json","captions.srt","cover.jpg"):
            if not (folder/file).is_file():
                failed.append(f"Missing render sidecar: {file}")
        if video.stat().st_size<200_000:
            failed.append("Video file too small")
        if (folder/"metadata.json").is_file():
            meta=json.loads((folder/"metadata.json").read_text(encoding="utf-8"))
            visual_sources=meta.get("visuals",[])
            if len(visual_sources)!=len(scenes) or any(x.get("source")!="local" for x in visual_sources):
                failed.append("Unexpected renderer visual source; gradient or external replacement detected")
            if "PurffleStudios" in json.dumps(meta):
                failed.append("Renderer default brand remains")
            if any("by" in item.get("source",{}).get("license","").casefold() for item in scenes) and \
                    "Photo credits:" not in meta.get("description",""):
                failed.append("Missing mandatory CC BY photographer credits")
        info=subprocess.run(["ffprobe","-v","error","-show_entries",
                             "stream=codec_type,width,height:format=duration",
                             "-of","json",str(video)],
                            check=True,capture_output=True,text=True,timeout=30)
        parsed=json.loads(info.stdout)
        v=[s for s in parsed.get("streams",[]) if s.get("codec_type")=="video"]
        a=[s for s in parsed.get("streams",[]) if s.get("codec_type")=="audio"]
        if len(v)!=1 or (v[0].get("width"),v[0].get("height"))!=(720,1280):
            failed.append("Expected 720×1280 vertical video")
        if not a:
            failed.append("Narration audio missing")
        if not 18<=float(parsed.get("format",{}).get("duration",0))<=65:
            failed.append("Short duration outside 18-65 seconds")
    reportfile=root/"cinematic_report.json"
    if not reportfile.is_file():
        failed.append("No documentary editing completion proof")
    else:
        report=json.loads(reportfile.read_text(encoding="utf-8"))
        if report.get("version")!="documentary-photo-1" or report.get("graphics")!="none":
            failed.append("Documentary must have ZERO programmatically drawn graphics")
        if report.get("image_policy")!="real-photos-only":
            failed.append("Documentary photo policy mismatch")
    result={"status":"FAIL" if failed else "PASS",
            "photo_scenes":len(scenes),"unique_photos":len(sources),
            "direct_scene_matches":direct,"no_svg_or_diagrams":True,
            "issues":failed,
            "limits":"License metadata and technical matching do not verify scientific accuracy, authenticity or monetization."}
    (root/"quality_report.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))
    if failed:
        raise SystemExit("PHOTO-ONLY QUALITY GATE FAILED: no upload allowed")


if __name__=="__main__":
    check()

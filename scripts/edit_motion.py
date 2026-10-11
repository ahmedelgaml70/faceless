#!/usr/bin/env python3
"""Edit actual moving stock clips into a narrated, captioned 9:16 Short.

Unlike the legacy slideshow editor, this video track is composed entirely
from licensed camera footage. Uses FFmpeg for honest trims/cuts and timing.
No vector/AI graphics, no fake motion or photo Ken Burns replacements.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import re
import subprocess
import sys

from cinematic_post import srt,groups,timeline,probe
from prepare_motion import probe_movie

FPS=24
W,H=720,1280


def run(cmd: list[str],timeout=160):
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=timeout)
    if p.returncode:
        raise RuntimeError("FFmpeg failed: "+p.stderr[-1350:])


def timecode(s: float) -> str:
    m,sec=divmod(max(0,s),60)
    h,m=divmod(int(m),60)
    return f"{h:02d}:{m:02d}:{sec:06.3f}".replace(".",",")


def write_subtitles(cues, destination: Path) -> None:
    with destination.open("w",encoding="utf-8") as out:
        for index,(start,end,text) in enumerate(cues,1):
            text=" ".join(text.split())
            if not text or end<=start:
                continue
            # Avoid platform UI overlays: subtitle always in lower-middle.
            out.write(f"{index}\n{timecode(start)} --> {timecode(end)}\n{text}\n\n")


def compile_video(root: Path):
    base=root/"prepared"
    plan=json.loads((base/"motion_manifest.json").read_text(encoding="utf-8"))
    script=json.loads((base/"script.json").read_text(encoding="utf-8"))
    scenes=plan["scenes"]
    video_list=list((root/"output_videos").glob("*/short.mp4"))
    if len(video_list)!=1:
        raise RuntimeError("Need one PurffleShorts rendered narration MP4")
    target=video_list[0]
    folder=target.parent
    duration=probe(target)
    timed_words=srt(folder/"captions.srt")
    if len(timed_words)<5:
        raise RuntimeError("Narration caption synchronization missing")
    boundaries=timeline(script,timed_words,duration)
    if len(boundaries)!=len(scenes)+1:
        raise RuntimeError("Clip/scene narration alignment mismatch")
    if any(boundaries[i+1]-boundaries[i]<2 for i in range(len(scenes))):
        raise RuntimeError("Scene would cut too quickly to follow narration")

    temporary=folder/"motion_work"
    temporary.mkdir(exist_ok=True)
    parts=[]
    for index,shot in enumerate(scenes):
        original=root/shot["clip"]
        if not original.exists():
            raise RuntimeError(f"Moving footage missing: {original}")
        span=boundaries[index+1]-boundaries[index]
        if shot["duration"]<span+0.2:
            raise RuntimeError(f"Source video too short for narration scene {index+1}: "
                               f"{shot['duration']:.1f}s footage vs {span:.1f}s narration")
        # Offset trims within each verified clip to avoid standard stock openings.
        headroom=shot["duration"]-span
        start=min(1.8, max(0,headroom*0.22))
        output=temporary/f"shot_{index:02d}.mp4"
        # Wide shots cannot be cropped to 9:16 without losing 2/3 of the
        # actual waterfall. Retain the full sharp VIDEO in the foreground,
        # over a darkened, softly blurred duplicate of the SAME MOVING CLIP.
        # Both layers are documentary frames, never synthetic SVG artwork.
        dim=probe_movie(original)
        if dim["width"]/max(1,dim["height"])>=0.83:
            filt=(
                f"[0:v]split=2[bg][fg];"
                f"[bg]scale={W}:{H}:force_original_aspect_ratio=increase,"
                f"crop={W}:{H},boxblur=17:2,eq=brightness=-0.16[back];"
                f"[fg]scale={W}:980:force_original_aspect_ratio=decrease,setsar=1[sharp];"
                f"[back][sharp]overlay=(W-w)/2:(H-h)/2:shortest=1,"
                f"fps={FPS},format=yuv420p[out]"
            )
            render_filter=["-filter_complex",filt,"-map","[out]"]
        else:
            filt=(f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                  f"crop={W}:{H},setsar=1,fps={FPS},format=yuv420p")
            render_filter=["-vf",filt]
        run(["ffmpeg","-hide_banner","-loglevel","error","-y",
             "-ss",f"{start:.3f}","-i",str(original),
             "-t",f"{span:.3f}",*render_filter,
             "-an","-c:v","libx264","-preset","veryfast","-crf","20",
             "-g","48","-r",str(FPS),str(output)],timeout=140)
        parts.append(output)
        print(f"MOVING CUT {index+1}/{len(scenes)}: "
              f"{shot['source']['title'][:45]} ({span:.1f}s)",flush=True)

    concat=temporary/"concat.txt"
    concat.write_text("".join(f"file '{file.resolve().as_posix()}'\n" for file in parts),
                      encoding="utf-8")
    silent=temporary/"reel.mp4"
    run(["ffmpeg","-hide_banner","-loglevel","error","-y",
         "-f","concat","-safe","0","-i",str(concat),
         "-c","copy","-movflags","+faststart",str(silent)],timeout=60)
    subtitle_file=temporary/"clean_captions.srt"
    write_subtitles(groups(timed_words),subtitle_file)

    original=folder/"voice_source.mp4"
    target.replace(original)
    temp=folder/"motion_finish.mp4"
    # Track 0 is genuine B-roll, track 1 is only the Kokoro voice (stock audio muted).
    # FFmpeg/libass renders text subtitles, not diagrams or generated illustrations.
    # libass maps style values from its virtual PlayResY to output pixels.
    # Prior FontSize=30, MarginV=180 inadvertently produced giant top captions.
    # These smaller values place natural-size captions in the lower-safe area.
    subtitles_filter=(
        "subtitles="+str(subtitle_file.relative_to(root)).replace("\\","/")+
        ":force_style='FontName=DejaVu Sans,FontSize=12,Alignment=2,"
        "MarginV=44,Outline=1,Shadow=1,BorderStyle=1,"
        "PrimaryColour=&H00FFFFFF'"
    )
    try:
        run(["ffmpeg","-hide_banner","-loglevel","error","-y",
             "-i",str(silent),"-i",str(original),
             "-map","0:v:0","-map","1:a:0",
             "-vf",subtitles_filter,
             "-c:v","libx264","-preset","veryfast","-crf","20",
             "-pix_fmt","yuv420p","-c:a","aac","-b:a","128k",
             "-shortest","-movflags","+faststart",str(temp)],timeout=180)
        if not temp.exists() or temp.stat().st_size<400_000:
            raise RuntimeError("Finished moving-video output too small")
        if abs(probe(temp)-duration)>1.6:
            raise RuntimeError("Final moving-video duration mismatches voice narration")
        temp.replace(target)
        original.unlink(missing_ok=True)
        print(f"REAL MOTION COMPLETE: {target}, {len(scenes)} original licensed moving clips")
        report={
            "version":"real-motion-1","source":"licensed-camera-video-only",
            "graphics":"subtitles-only","moving_scenes":len(scenes),
            "duration":duration,"asset_ids":[s["source"]["id"] for s in scenes],
            "editing":"hard documentary cuts + text-only timed subtitles"
        }
        (base/"cinematic_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    finally:
        if not target.exists() and original.exists():
            original.replace(target)
        for file in temporary.glob("*"):
            file.unlink(missing_ok=True)
        temporary.rmdir()


if __name__=="__main__":
    compile_video(Path(sys.argv[1]) if len(sys.argv)>1 else Path.cwd())

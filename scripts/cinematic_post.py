#!/usr/bin/env python3
"""Photo-led documentary finishing pass.

No SVG, programmatic shapes, diagrams, HUDs, artificial science animations,
rendered illustrations, or graphics. Every scene is a licensed REAL photograph.
Only restrained photographic camera moves, clean timed subtitles and crossfades.
Preserves the existing Kokoro speech/audio track.
"""
from __future__ import annotations

import bisect
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps

W,H,FPS=720,1280,24
FONT="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def clip(v: float, low: float=0.0, high: float=1.0) -> float:
    return min(high,max(low,v))


def probe(path: Path) -> float:
    cp=subprocess.run(["ffprobe","-v","error","-show_entries",
                       "format=duration","-of",
                       "default=noprint_wrappers=1:nokey=1",str(path)],
                      capture_output=True,text=True,check=True,timeout=20)
    return float(cp.stdout.strip())


def srt(path: Path) -> list[tuple[float,float,str]]:
    text=path.read_text(encoding="utf-8-sig")
    out=[]
    def seconds(val: str) -> float:
        h,m,s=val.strip().split()[0].replace(",",".").split(":")
        return 3600*int(h)+60*int(m)+float(s)
    for block in re.split(r"\n\s*\n",text.strip()):
        lines=block.splitlines()
        match=next((i for i,t in enumerate(lines) if "-->" in t),None)
        if match is None:
            continue
        try:
            left,right=lines[match].split("-->",1)
            a,b=seconds(left),seconds(right)
        except (ValueError,IndexError):
            continue
        caption=re.sub(r"<[^>]*>","", " ".join(lines[match+1:])).strip()
        if a<b and caption:
            out.append((a,b,caption))
    return out


def groups(cues: list[tuple[float,float,str]]) -> list[tuple[float,float,str]]:
    """Merge word-synced SRT chunks into short human-readable statements."""
    out=[]
    words=[]
    start=end=0.0
    for a,b,text in cues:
        if words and (len(" ".join(words).split())+len(text.split())>6 or b-start>1.85):
            out.append((start,end," ".join(words)))
            words=[]
        if not words:
            start=a
        words.append(text)
        end=b
    if words:
        out.append((start,end," ".join(words)))
    return out


def timeline(script: dict, cues: list[tuple[float,float,str]], duration: float):
    scenes=script["scenes"]
    counts=[max(1,len(re.findall(r"\b\w+\b",x["narration"]))) for x in scenes]
    cumulative=[0]
    for n in counts:
        cumulative.append(cumulative[-1]+n)
    word_segments=[]
    position=0
    for a,b,t in cues:
        n=max(1,len(re.findall(r"\b\w+\b",t)))
        word_segments.extend(((position,a),(position+n,b)))
        position+=n
    anchors=[x[0] for x in word_segments]
    times=[0.0]
    for idx in range(1,len(scenes)):
        where=cumulative[idx]/cumulative[-1]
        if position and anchors:
            desired=where*position
            j=bisect.bisect_left(anchors,desired)
            if j==0:
                sec=word_segments[0][1]
            elif j>=len(anchors):
                sec=word_segments[-1][1]
            else:
                p0,t0=word_segments[j-1]
                p1,t1=word_segments[j]
                sec=t0+(desired-p0)*(t1-t0)/max(.01,p1-p0)
        else:
            sec=duration*where
        times.append(min(duration-.4,max(times[-1]+.5,sec)))
    return times+[duration]


def photo_frame(photo: Image.Image, elapsed: float, length: float, idx: int) -> Image.Image:
    f=clip(elapsed/max(.1,length))
    # Gentle Ken Burns, not an artificial animated diagram.
    zoom=1.04+.055*f
    width,height=int(W*zoom),int(H*zoom)
    enlarged=photo.resize((width,height),Image.Resampling.BICUBIC)
    x_span=width-W
    y_span=height-H
    if idx%2:
        x=int(x_span*(.1+.8*f))
        y=int(y_span*(.75-.5*f))
    else:
        x=int(x_span*(.9-.8*f))
        y=int(y_span*(.25+.5*f))
    return enlarged.crop((x,y,x+W,y+H))


def shade_lower(frame: Image.Image) -> Image.Image:
    # Pure tonal shading for text legibility; no drawn graphic elements.
    mask=Image.new("L",(1,H))
    pixels=mask.load()
    for y in range(H):
        strength=clip((y-710)/425)
        pixels[0,y]=int(185*strength*strength)
    grad=Image.new("RGB",(W,H),"#06101b")
    return Image.composite(grad,frame,mask.resize((W,H)))


def split_caption(draw: ImageDraw.ImageDraw,text: str,face,max_w: int=590) -> list[str]:
    parts=[]
    current=""
    for word in text.split():
        text_to_try=(current+" "+word).strip()
        if current and draw.textbbox((0,0),text_to_try,font=face)[2]>max_w:
            parts.append(current)
            current=word
        else:
            current=text_to_try
    if current:
        parts.append(current)
    return parts[:3]


def captions_on(frame: Image.Image, words: str) -> Image.Image:
    if not words:
        return frame
    draw=ImageDraw.Draw(frame)
    size=52 if len(words)<34 else 44
    face=ImageFont.truetype(FONT,size)
    text=" ".join(words.strip().split())
    rows=split_caption(draw,text,face)
    y=H-290-len(rows)*60
    # Text-only captions: no cards, vector ornaments or progress graphics.
    for line in rows:
        box=draw.textbbox((0,0),line,font=face,stroke_width=3)
        x=(W-(box[2]-box[0]))//2
        draw.text((x,y),line,font=face,fill="#ffffff",
                  stroke_width=4,stroke_fill="#07111d")
        y+=60
    return frame


def main(root: Path) -> None:
    videos=list(root.glob("output_videos/*/short.mp4"))
    if len(videos)!=1:
        raise RuntimeError(f"Expected exactly one PurffleShorts video, got {len(videos)}")
    path=videos[0]
    folder=path.parent
    script=json.loads((root/"prepared/script.json").read_text(encoding="utf-8"))
    manifest=json.loads((root/"prepared/visual_manifest.json").read_text(encoding="utf-8"))
    scenes=manifest["scenes"]
    if len(scenes)!=len(script["scenes"]):
        raise RuntimeError("Mismatch between script and visual scenes")
    if not all(s["kind"]=="wikimedia-photo" for s in scenes):
        raise RuntimeError("Non-photographic visual encountered: fail closed")

    photos=[]
    for scene in scenes:
        file=root/scene["asset"]
        if not file.is_file():
            raise FileNotFoundError(file)
        with Image.open(file) as pic:
            photos.append(ImageEnhance.Contrast(
                ImageOps.fit(pic.convert("RGB"),(W,H))).enhance(1.04))
    duration=probe(path)
    cues=srt(folder/"captions.srt")
    if not cues:
        raise RuntimeError("No captions found; cannot produce captioned video")
    subtitle_groups=groups(cues)
    boundaries=timeline(script,cues,duration)
    original=folder/"source_with_audio.mp4"
    out=folder/"photo_finished_temp.mp4"
    os.replace(path,original)
    cmd=["ffmpeg","-hide_banner","-loglevel","error","-y",
         "-f","rawvideo","-pix_fmt","rgb24","-s",f"{W}x{H}",
         "-r",str(FPS),"-i","pipe:0","-i",str(original),
         "-map","0:v:0","-map","1:a:0",
         "-c:v","libx264","-preset","veryfast","-crf","20",
         "-pix_fmt","yuv420p","-c:a","copy","-shortest",
         "-movflags","+faststart",str(out)]
    result={}
    try:
        error_path=folder/"photo_editor.log"
        with error_path.open("w",encoding="utf-8") as err:
            process=subprocess.Popen(cmd,stdin=subprocess.PIPE,
                                     stdout=subprocess.DEVNULL,stderr=err)
            for i in range(math.ceil(duration*FPS)):
                t=min(duration-.001,i/FPS)
                scene=max(0,min(len(scenes)-1,bisect.bisect_right(boundaries,t)-1))
                a,b=boundaries[scene:scene+2]
                frame=photo_frame(photos[scene],t-a,b-a,scene)
                # Short dissolve: real photo to real photo, nothing synthesized.
                if scene>0 and t-a<.22:
                    previous=photo_frame(photos[scene-1],boundaries[scene]-boundaries[scene-1],
                                         boundaries[scene]-boundaries[scene-1],scene-1)
                    frame=Image.blend(previous,frame,clip((t-a)/.22))
                caption=next((text for ca,cb,text in subtitle_groups
                              if ca-.04<=t<=cb+.06),"")
                frame=captions_on(shade_lower(frame),caption)
                try:
                    process.stdin.write(frame.tobytes())
                except BrokenPipeError as exc:
                    raise RuntimeError("Photo renderer terminated early") from exc
            process.stdin.close()
            code=process.wait(timeout=120)
            if code!=0:
                raise RuntimeError("FFmpeg: "+error_path.read_text(encoding="utf-8")[-1400:])
        if out.stat().st_size<200_000 or abs(probe(out)-duration)>1.0:
            raise RuntimeError("Video output corrupted or duration mismatched")
        os.replace(out,path)
        original.unlink(missing_ok=True)
        error_path.unlink(missing_ok=True)
        result={"version":"documentary-photo-1","fps":FPS,
                "frames":math.ceil(duration*FPS),"duration":duration,
                "scenes":len(scenes),"image_policy":"real-photos-only",
                "graphics":"none","caption_treatment":"text-only lower third"}
        (root/"prepared/cinematic_report.json").write_text(
            json.dumps(result,indent=2),encoding="utf-8")
        print(f"DOCUMENTARY PHOTO VIDEO: {path} / {len(scenes)} photo scenes / no SVG or illustrations")
    except Exception:
        if not path.exists() and original.exists():
            os.replace(original,path)
        raise


if __name__=="__main__":
    main(Path(sys.argv[1]) if len(sys.argv)>1 else Path.cwd())

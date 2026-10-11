#!/usr/bin/env python3
"""Cinematic post-production for PurffleShorts.

Replaces the visual track with animated, script-aware science visuals while
preserving the original, aligned Kokoro narration. Pure Pillow + FFmpeg, no
paid APIs, no Chromium or GPU required. Original sources stay documented.
"""
from __future__ import annotations

import bisect
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import subprocess
import sys

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

W, H, FPS = 720, 1280, 24
INK = "#081421"
WHITE = "#f5f8ff"
SKY = "#61d9fa"
GOLD = "#fbc568"
FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]
FONT_CACHE: dict[tuple[int, bool], ImageFont.FreeTypeFont] = {}


def font(size: int, bold: bool = True):
    key = (size, bold)
    if key not in FONT_CACHE:
        FONT_CACHE[key] = ImageFont.truetype(FONTS[0 if bold else 1], size)
    return FONT_CACHE[key]


def clamp(x: float, a: float = 0.0, b: float = 1.0) -> float:
    return min(b, max(a, x))


def smooth(x: float) -> float:
    x = clamp(x)
    return x * x * (3 - 2 * x)


def probe(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True, timeout=30
    )
    return float(result.stdout.strip())


def parse_srt(path: Path, duration: float) -> list[tuple[float, float, str]]:
    if not path.exists():
        return [(0.0, duration, "")]
    data = path.read_text(encoding="utf-8-sig")
    entries = []
    for block in re.split(r"\n\s*\n", data.strip()):
        rows = [x.strip() for x in block.splitlines() if x.strip()]
        ix = next((i for i, x in enumerate(rows) if "-->" in x), None)
        if ix is None:
            continue
        try:
            left, right = rows[ix].split("-->", 1)
            def seconds(s: str) -> float:
                s = s.strip().replace(",", ".").split()[0]
                a, b, c = s.split(":")
                return int(a) * 3600 + int(b) * 60 + float(c)
            t0, t1 = seconds(left), seconds(right)
            txt = re.sub(r"<[^>]*>", "", " ".join(rows[ix+1:])).strip()
            if txt and t1 > t0:
                entries.append((t0, min(duration, t1), txt))
        except (ValueError, IndexError):
            continue
    return entries


def captions_grouped(entries: list[tuple[float, float, str]]) -> list[tuple[float, float, str]]:
    """Keep short readable phrases, instead of 1-word jittering captions."""
    out = []
    current = []
    st = en = 0.0
    for start, end, text in entries:
        if not current:
            st = start
        if current and (len(" ".join(current).split()) + len(text.split()) > 7
                        or end - st > 1.65):
            out.append((st, en, " ".join(current)))
            current, st = [], start
        current.append(text)
        en = end
    if current:
        out.append((st, en, " ".join(current)))
    return out


def caption_for(t: float, entries: list[tuple[float, float, str]]) -> tuple[str, float]:
    for st, en, text in entries:
        if st - 0.05 <= t <= en + 0.07:
            return text, smooth((t - st) / 0.22)
    return "", 1.0


def scene_spans(script: dict, duration: float, raw_cues: list[tuple[float, float, str]]) -> list[float]:
    """Use word counts and actual caption times to estimate narration cuts."""
    scenes = script.get("scenes") or []
    if not scenes:
        raise ValueError("No script scenes")
    scene_words = [max(1, len(re.findall(r"\b\w+\b", s.get("narration", "")))) for s in scenes]
    total = sum(scene_words)
    starts = [0.0]
    # Interpolate relative word position to real caption timeline when available.
    timeline = []
    position = 0
    for st, en, txt in raw_cues:
        n = max(1, len(re.findall(r"\b\w+\b", txt)))
        timeline.append((position, st))
        position += n
        timeline.append((position, en))
    boundaries = sorted(timeline)
    for idx in range(1, len(scenes)):
        fraction = sum(scene_words[:idx]) / total
        if boundaries and position:
            target = fraction * position
            j = bisect.bisect_left([x[0] for x in boundaries], target)
            if j <= 0:
                time = boundaries[0][1]
            elif j >= len(boundaries):
                time = boundaries[-1][1]
            else:
                p0, a = boundaries[j-1]
                p1, b = boundaries[j]
                time = a + ((target - p0) / max(1, p1 - p0)) * (b - a)
        else:
            time = duration * fraction
        starts.append(min(duration-0.5, max(starts[-1]+0.7, time)))
    starts.append(duration)
    return starts


def scene_category(search: str, narration: str) -> str:
    s = (search + " " + narration).casefold()
    if "balloon" in s:
        return "balloon"
    for category, words in [
        ("lightning", ("lightning", "electric", "bolt", "spark")),
        ("heat", ("temperature", "heat", "hotter", "degree", "sun surface", "superheat")),
        ("shockwave", ("shockwave", "shock wave", "explode", "expansion", "balloon", "pressure")),
        ("sound", ("thunder", "sonic", "sound", "noise", "echo", "vibration")),
        ("space", ("galaxy", "orbit", "planet", "moon", "cosmos", "space", "astronaut", "star")),
        ("weather", ("storm", "cloud", "weather", "rain", "atmosphere")),
        ("water", ("water", "ocean", "sea", "wave", "tide")),
        ("biology", ("molecule", "cell", "animal", "heart", "blood", "organism", "plant", "biology")),
        ("motion", ("aircraft", "plane", "jet", "speed", "flight", "engine")),
    ]:
        if any(w in s for w in words):
            return category
    return "diagram"


def scene_label(query: str, narration: str, category: str) -> str:
    labels = {
        "lightning": "THE ELECTRIC FLASH",
        "heat": "EXTREME HEAT",
        "shockwave": "RAPID EXPANSION",
        "balloon": "LIKE A BURSTING BALLOON",
        "sound": "THE SOUND WAVE",
        "space": "IN SPACE",
        "weather": "THE ATMOSPHERE",
        "water": "WAVE MOTION",
        "biology": "LIFE UNDER THE LENS",
        "motion": "FORCES IN MOTION",
        "diagram": "THE EXPLANATION",
    }
    return labels.get(category, "THE EXPLANATION")


def wrapped(draw: ImageDraw.ImageDraw, text: str, max_width: int, fnt, limit: int = 3) -> list[str]:
    lines, line = [], ""
    for token in text.strip().split():
        trial = (line + " " + token).strip()
        if draw.textbbox((0, 0), trial, font=fnt)[2] > max_width and line:
            lines.append(line)
            line = token
        else:
            line = trial
    if line:
        lines.append(line)
    return lines[:limit]


def scene_background(photo: Image.Image) -> Image.Image:
    photo = ImageOps.exif_transpose(photo).convert("RGB")
    # Blur-based full-bleed background, high-detail foreground with no black bars.
    cover = ImageOps.fit(photo, (W, H), method=Image.Resampling.LANCZOS)
    # The prepared art already contains a carefully positioned sharp image.
    # Do NOT blur the full frame; that hid the actual footage in version 1.
    return ImageEnhance.Color(cover).enhance(1.10)


def gradient_mask() -> Image.Image:
    mask = Image.new("RGBA", (W, H))
    pixels = mask.load()
    for y in range(H):
        if y < 170:
            alpha = int(105 * (1-y/170))
        elif y > 785:
            alpha = int(35 + 175 * clamp((y-785)/425))
        else:
            alpha = 12
        for x in range(W):
            pixels[x, y] = (2, 9, 19, min(230, alpha))
    return mask


GRADIENT = gradient_mask()


def pan_photo(photo: Image.Image, t: float, start: float, end: float, idx: int) -> Image.Image:
    f = clamp((t-start) / max(.01, end-start))
    zoom = 1.065 + 0.085 * smooth(f)
    tw, th = int(W*zoom), int(H*zoom)
    base = photo.resize((tw, th), Image.Resampling.BICUBIC)
    shift = int(11 * math.sin(t*.36 + idx*.9))
    ox = (tw-W)//2 + shift
    oy = (th-H)//2 + int(12*math.sin(t*.27+idx))
    ox = max(0, min(tw-W, ox))
    oy = max(0, min(th-H, oy))
    return base.crop((ox, oy, ox+W, oy+H))


def draw_rings(d: ImageDraw.ImageDraw, t: float, color: str, cx=355, cy=580) -> None:
    for j in range(4):
        phase = ((t*.46 + j/4) % 1.0)
        radius = int(80 + 280*phase)
        brightness = int(140*(1-phase)+30)
        d.arc((cx-radius,cy-radius,cx+radius,cy+radius), 210, 514,
              fill=(*Image.new("RGB",(1,1),color).getpixel((0,0)),brightness), width=4)


def draw_science(layer: Image.Image, category: str, t: float, scene_elapsed: float, idx: int) -> None:
    """Animated scientific accents: bespoke shapes instead of generic wallpaper."""
    d = ImageDraw.Draw(layer, "RGBA")
    s = scene_elapsed
    if category == "lightning":
        opacity = 210 if (int(s*5) % 17) in (0, 1, 5) else 80
        pts = [(410, 250), (310, 440), (392, 452), (235, 680), (288, 494), (230, 484)]
        d.line(pts, fill=(111, 229, 255, opacity//4), width=37, joint="curve")
        d.line(pts, fill=(243, 251, 255, opacity), width=10, joint="curve")
        draw_rings(d, s, SKY, 330, 540)
    elif category == "balloon":
        inflate = smooth(min(1.0, s/2.2))
        size = int(130 + 135*inflate)
        x, y = 355, 540
        d.ellipse((x-size,y-size,x+size,y+size),fill=(52,136,196,85),
                  outline=(151,233,253,205),width=7)
        d.ellipse((x-size//2,y-size//2,x-size//2+85,y-size//2+140),
                  outline=(230,249,255,110),width=8)
        d.line((x,y+size,x+20,y+size+95), fill=(245,222,171,175), width=5)
        if s>2.0:
            for j in range(9):
                a=j*math.tau/9
                xx=int(x+((s-2)*120+size)*math.cos(a))
                yy=int(y+((s-2)*120+size)*math.sin(a))
                d.ellipse((xx-8,yy-8,xx+8,yy+8),fill=(151,233,253,180))
    elif category == "weather":
        for x,y,r in ((230,465,100),(340,410,135),(475,470,110)):
            d.ellipse((x-r,y-r,x+r,y+r),fill=(104,158,198,45),
                      outline=(170,217,239,110),width=4)
        for j in range(6):
            x=175+j*69+int(s*17)%35
            y=650+j%3*40+int(s*27)%70
            d.line((x,y,x-22,y+58),fill=(134,213,250,140),width=5)
    elif category in ("shockwave", "sound", "water"):
        for k in range(5):
            ph = (s*.36 + k*.2) % 1
            radius = int(75 + ph*405)
            alpha = int(150*(1-ph))
            d.ellipse((360-radius, 550-radius,360+radius,550+radius),
                      outline=(74,208,250,alpha), width=4)
        if category != "shockwave":
            for line in range(3):
                points = [(x, int(530+line*85 + 19*math.sin(x*.025-s*4+line))) for x in range(75,650,9)]
                d.line(points, fill=(155,233,255,125), width=5, joint="curve")
    elif category == "heat":
        h = int(290*(.35 + .65 * smooth(s/3)))
        d.rounded_rectangle((320,295,375,720),radius=26,outline=(255,229,170,130),width=5)
        d.rounded_rectangle((328,714-h,367,714),radius=14,fill=(255,179,74,175))
        d.ellipse((306,694,389,777),fill=(255,145,60,160))
        for j in range(4):
            a = s*1.8 + j*1.5
            x = 245+j*89+12*math.sin(a)
            y = int(510 - 65*math.sin(a*.8))
            d.arc((x-20,y-45,x+20,y+45),40,250,fill=(255,210,127,145),width=5)
    elif category == "space":
        d.ellipse((218,385,498,665),fill=(40,98,164,70),outline=(112,217,245,170),width=5)
        d.arc((110,440,615,690),10,340,fill=(236,201,136,180),width=8)
        x = int(360+255*math.cos(s*.65))
        y = int(560+118*math.sin(s*.65))
        d.ellipse((x-20,y-20,x+20,y+20),fill=(248,222,156,220))
    elif category == "biology":
        dots = [(360+int(170*math.cos(j*math.pi/3+s*.12)),
                 560+int(170*math.sin(j*math.pi/3+s*.12))) for j in range(6)]
        for a,b in zip(dots,dots[1:]+dots[:1]):
            d.line((a,b),fill=(100,210,246,105),width=5)
        for x,y in dots:
            d.ellipse((x-24,y-24,x+24,y+24),fill=(112,219,239,160))
    elif category == "motion":
        x = 220+int(35*math.sin(s*.9))
        d.polygon([(x,560),(x+360,540),(x+375,565),(x+360,586)],fill=(212,242,255,150))
        d.polygon([(x+185,562),(x+70,665),(x+260,570)],fill=(91,187,237,140))
        for k in range(3):
            y = 560 + k*45
            d.line((x-40-int(s*24)%70,y,x-160-int(s*24)%70,y),fill=(124,219,248,115),width=4)
    else:
        for j in range(3):
            x=int(200+155*math.cos(s*.4+j*2.094))
            y=int(560+160*math.sin(s*.4+j*2.094))
            d.ellipse((x-18,y-18,x+18,y+18),fill=(99,209,244,135))
        d.ellipse((180,380,540,740),outline=(102,201,245,125),width=5)


def draw_frame(photo: Image.Image, category: str, label: str, idx: int,
               scenes_n: int, t: float, start: float, end: float, duration: float,
               caption: str, cap_in: float, is_photo: bool) -> Image.Image:
    img = pan_photo(photo, t, start, end, idx).convert("RGBA")
    img = Image.alpha_composite(img, GRADIENT)

    fx = Image.new("RGBA", (W, H), (0,0,0,0))
    draw_science(fx, category, t, t-start, idx)
    # A real licensed photograph should be the hero; animated HUD elements are
    # deliberately subtle on top of photos and stronger on original diagrams.
    if is_photo:
        fx.putalpha(fx.getchannel("A").point(lambda a: int(a * 0.30)))
    img = Image.alpha_composite(img, fx)
    d = ImageDraw.Draw(img, "RGBA")

    # Animated brand bar and reading progress.
    d.rounded_rectangle((38,56,240,100),radius=16,fill=(8,23,39,215))
    d.text((60,66),"F / SCIENCE",font=font(20),fill=WHITE)
    d.text((W-132,68),f"{idx+1:02d} / {scenes_n:02d}",font=font(20),fill=WHITE)
    d.rounded_rectangle((38,116,W-38,122),radius=3,fill=(100,150,180,65))
    d.rounded_rectangle((38,116,38+int((W-76)*clamp(t/duration)),122),radius=3,fill=(97,218,244,235))

    # Small, consistent on-screen context above the actual scientific imagery.
    d.text((45,168),label,font=font(26),fill=GOLD,stroke_width=1,stroke_fill=(8,20,33,120))
    d.line((45,212,160,212),fill=(251,197,104,200),width=4)

    # Subtitle card deliberately placed in the safe lower third, never center.
    if caption:
        y_base = 948
        f = font(44)
        lines = wrapped(d, caption.upper(), 616, f, limit=3)
        box_h = max(116, 34+len(lines)*61)
        left, top, right, bottom = 30,y_base-10,690,y_base-10+box_h
        pop = 6*(1-cap_in)
        top += pop
        d.rounded_rectangle((left,top,right,bottom+pop),radius=22,
                            fill=(5,16,30,int(225*max(.65,cap_in))))
        d.rounded_rectangle((left,top,right,bottom+pop),radius=22,
                            outline=(108,201,235,85),width=2)
        for j,line in enumerate(lines):
            bbox = d.textbbox((0,0),line,font=f)
            x=(W-(bbox[2]-bbox[0]))//2
            y=int(top+22+j*61)
            d.text((x+2,y+3),line,font=f,fill=(0,0,0,175),stroke_width=2)
            d.text((x,y),line,font=f,fill=WHITE)
        d.rounded_rectangle((50,bottom+pop-11,50+int(580*clamp((t-start)/(end-start))),bottom+pop-6),
                            radius=2,fill=(251,197,104,210))

    # Cinematic fast cross-dip avoids abruptly cutting a zooming image.
    fade = min(clamp((t-start)/.16), clamp((end-t)/.18))
    if fade < 1:
        dark = Image.new("RGBA",(W,H),(0,7,18,int((1-smooth(fade))*190)))
        img=Image.alpha_composite(img,dark)
    return img.convert("RGB")


def render(root: Path) -> None:
    videos = sorted(root.glob("output_videos/*/short.mp4"))
    if len(videos) != 1:
        raise RuntimeError(f"Expected exactly one rendered video, found {len(videos)}")
    video=videos[0]
    folder=video.parent
    script=json.loads((root/"prepared/script.json").read_text(encoding="utf-8"))
    manifest=json.loads((root/"prepared/visual_manifest.json").read_text(encoding="utf-8"))
    scenes=script["scenes"]
    if len(scenes)!=len(manifest["scenes"]):
        raise RuntimeError("Script/visual plan mismatch")
    duration=probe(video)
    raw=parse_srt(folder/"captions.srt",duration)
    display_cues=captions_grouped(raw)
    span=scene_spans(script,duration,raw)
    base=[]
    for entry in manifest["scenes"]:
        p=Path(entry["asset"])
        if not p.is_file():
            raise RuntimeError(f"Missing visual {p}")
        with Image.open(p) as im:
            base.append(scene_background(im))
    total_frames=math.ceil(duration*FPS)
    original=folder/"original_render.mp4"
    polished=folder/"cinematic_temp.mp4"
    os.replace(video,original)
    logfile=folder/"cinematic_ffmpeg.log"
    cmd=[
        "ffmpeg","-hide_banner","-loglevel","error","-y",
        "-f","rawvideo","-pix_fmt","rgb24","-s",f"{W}x{H}","-r",str(FPS),
        "-i","pipe:0","-i",str(original),
        "-map","0:v:0","-map","1:a:0",
        "-c:v","libx264","-preset","veryfast","-crf","20",
        "-pix_fmt","yuv420p","-c:a","copy","-shortest",
        "-movflags","+faststart",str(polished)]
    try:
        with logfile.open("w",encoding="utf-8") as err:
            proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=err)
            for frame in range(total_frames):
                t=min(duration-.001,frame/FPS)
                idx=max(0,min(len(scenes)-1,bisect.bisect_right(span,t)-1))
                m=manifest["scenes"][idx]
                caption,cap_in=caption_for(t,display_cues)
                category=scene_category(m["query"],scenes[idx]["narration"])
                label=scene_label(m["query"],scenes[idx]["narration"],category)
                img=draw_frame(base[idx],category,label,idx,len(scenes),t,
                               span[idx],span[idx+1],duration,caption,cap_in,
                               m["kind"] == "wikimedia-commons")
                try:
                    proc.stdin.write(img.tobytes())
                except BrokenPipeError as exc:
                    raise RuntimeError("FFmpeg cinematic renderer ended early") from exc
            proc.stdin.close()
            rc=proc.wait(timeout=180)
            if rc:
                raise RuntimeError(f"FFmpeg cinematic render failed: {logfile.read_text()[-1500:]}")
        if not polished.exists() or polished.stat().st_size < 200_000:
            raise RuntimeError("Polished video was not generated correctly")
        if abs(probe(polished)-duration) > 1.0:
            raise RuntimeError("Cinematic video duration does not match narration")
        os.replace(polished,video)
        original.unlink(missing_ok=True)
        logfile.unlink(missing_ok=True)
        report={"version":"cinematic-1","fps":FPS,"frames":total_frames,
                "scene_types":[scene_category(m["query"],scenes[i]["narration"])
                               for i,m in enumerate(manifest["scenes"])],
                "duration":duration,"source":"licensed Commons and/or original diagrams"}
        (root/"prepared/cinematic_report.json").write_text(json.dumps(report,indent=2))
        print(f"CINEMATIC VIDEO: {video}; {total_frames} frames; {len(scenes)} animated scenes")
    except Exception:
        # Preserve source for debugging, never leave a partial new video.
        if not video.exists() and original.exists():
            os.replace(original,video)
        raise


if __name__=="__main__":
    render(Path(sys.argv[1]) if len(sys.argv)>1 else Path.cwd())

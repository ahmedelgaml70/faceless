#!/usr/bin/env python3
"""Find real licensed moving video, verify frames with Gemini, THEN write script.

Sources: Wikimedia Commons videos (no key); optionally Pexels free API if a
PEXELS_API_KEY Actions secret is configured. Never generate SVGs, drawings,
still-photo sequences, AI image/video, or animated diagram substitutes.
A video run fails rather than produce a slideshow.
"""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.parse

import requests
from PIL import Image, ImageOps

from prepare_content import (
    COMMONS, HEADERS, MEDIA, PREPARED, BAD_TITLE, plain, rights,
    stems, VisionReview, full_frame_photo,
)
from prepare_storyboard import Shot, subject_search, write_visual_script, perceptual_hash

LOG=logging.getLogger("faceless.motion")
CLIPS=5
MIN_CLIPS=4
MAX_REVIEWS=13
PER_FILE_LIMIT=22_000_000
ALLOWED_HOSTS={"upload.wikimedia.org", "player.vimeo.com", "videos.pexels.com",
               "cdn.pexels.com", "player.pexels.com", "static-videos.pexels.com"}


def json_request(url: str, params: dict, headers: dict | None=None):
    r=requests.get(url,params=params,headers=headers or HEADERS,timeout=25)
    r.raise_for_status()
    return r.json()


def commons_sources(phrase: str) -> list[dict]:
    params={
        "action":"query","generator":"search",
        "gsrsearch":f"{phrase} filetype:video",
        "gsrnamespace":6,"gsrlimit":35,
        "prop":"imageinfo",
        "iiprop":"url|size|mime|extmetadata",
        "iiurlwidth":500,
        "format":"json","formatversion":2,
    }
    found=json_request(COMMONS,params).get("query",{}).get("pages",[])
    result=[]
    for page in found:
        name=page.get("title","")
        if any(bad in name.casefold() for bad in BAD_TITLE):
            continue
        info=(page.get("imageinfo") or [{}])[0]
        mime=info.get("mime","")
        if mime not in {"video/webm","video/ogg","video/mp4","application/ogg"}:
            continue
        permission=rights(info.get("extmetadata") or {})
        if not permission:
            continue
        link=info.get("url","")
        parsed=urllib.parse.urlsplit(link)
        if parsed.scheme!="https" or parsed.hostname!="upload.wikimedia.org":
            continue
        artist=plain((info.get("extmetadata") or {}).get("Artist",{}).get("value","")) or "Unknown"
        if "by" in permission[0].casefold() and artist=="Unknown":
            continue
        poster=info.get("thumburl","")
        result.append({
            "provider":"Wikimedia Commons","id":name,"title":name,
            "artist":artist,"page":info.get("descriptionurl",""),
            "license":permission[0],"license_url":permission[1],
            "url":link,"poster":poster,
            "size":info.get("size",0), "mime":mime,
            "file_links":commons_downloads(link,info.get("size",0)),
        })
    return result


def commons_downloads(link: str, size: int) -> list[str]:
    # Wikimedia's TimedMediaHandler publishes lower-bandwidth WebM versions.
    # Each candidate is checked server-side when downloading.
    p=urllib.parse.urlsplit(link)
    if "/wikipedia/commons/" not in p.path:
        return [link] if size<=PER_FILE_LIMIT else []
    base=p.path.rsplit("/",1)[-1]
    head=p.path.replace("/wikipedia/commons/","/wikipedia/commons/transcoded/",1)
    choices=[
        f"https://upload.wikimedia.org{head}/{base}.{quality}"
        for quality in ("480p.vp9.webm","480p.webm","360p.webm","360p.vp9.webm","240p.vp9.webm")
    ]
    if size and size<=PER_FILE_LIMIT:
        choices.append(link)
    return choices


def pexels_sources(phrase: str) -> list[dict]:
    key=os.environ.get("PEXELS_API_KEY","").strip()
    if not key:
        return []
    payload=json_request(
        "https://api.pexels.com/v1/videos/search",
        {"query":phrase,"per_page":20,"size":"small"},
        {"Authorization":key,"User-Agent":HEADERS["User-Agent"]}
    )
    out=[]
    for video in payload.get("videos",[]):
        duration=int(video.get("duration") or 0)
        if not 5<=duration<=120:
            continue
        files=[f for f in video.get("video_files",[])
               if f.get("file_type")=="video/mp4" and f.get("link")
               and int(f.get("width") or 0)>=480 and int(f.get("height") or 0)>=480]
        files.sort(key=lambda f:(0 if f.get("height",0)>f.get("width",0) else 1,
                                  abs(int(f.get("width",0))-720)+abs(int(f.get("height",0))-1280)))
        if not files:
            continue
        creator=video.get("user") or {}
        out.append({
            "provider":"Pexels","id":str(video["id"]),
            "title":f"Pexels nature video {video['id']}: {phrase}",
            "artist":creator.get("name","Pexels contributor"),
            "page":video.get("url",""),"license":"Pexels License",
            "license_url":"https://www.pexels.com/license/",
            "url":files[0]["link"],
            "poster":video.get("image",""),
            "duration":duration,"file_links":[f["link"] for f in files[:2]],
        })
    return out


def safe_host(url: str) -> bool:
    p=urllib.parse.urlsplit(url)
    return p.scheme=="https" and (p.hostname or "") in ALLOWED_HOSTS


def download_clip(src: dict, target: Path) -> bool:
    for url in src["file_links"][:6]:
        if not safe_host(url):
            continue
        try:
            with requests.get(url,headers={"User-Agent":HEADERS["User-Agent"]},
                              timeout=(14,45),stream=True) as r:
                r.raise_for_status()
                if "text/html" in r.headers.get("Content-Type",""):
                    continue
                length=int(r.headers.get("Content-Length") or 0)
                if length>PER_FILE_LIMIT:
                    continue
                n=0
                with target.open("wb") as file:
                    for chunk in r.iter_content(chunk_size=262_144):
                        if not chunk:
                            continue
                        n+=len(chunk)
                        if n>PER_FILE_LIMIT:
                            raise ValueError("Video clip exceeds 22 MB limit")
                        file.write(chunk)
                if n>80_000:
                    return True
        except (requests.RequestException,ValueError,IOError) as error:
            LOG.debug("Source file rejected: %s",str(error)[:90])
        target.unlink(missing_ok=True)
    return False


def probe_movie(path: Path) -> dict:
    proc=subprocess.run(["ffprobe","-v","error","-show_entries",
                         "stream=codec_type,width,height:format=duration",
                         "-of","json",str(path)],
                        capture_output=True,text=True,timeout=25,check=True)
    parsed=json.loads(proc.stdout)
    stream=next((s for s in parsed.get("streams",[]) if s.get("codec_type")=="video"),{})
    return {
        "duration":float(parsed.get("format",{}).get("duration") or 0),
        "width":int(stream.get("width") or 0),
        "height":int(stream.get("height") or 0),
    }


def still_from_clip(path: Path, position: float) -> Image.Image:
    proc=subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-ss",
                         str(max(0,position)),"-i",str(path),"-frames:v","1",
                         "-vf","scale=480:-2","-f","image2pipe","-vcodec","mjpeg","pipe:1"],
                        capture_output=True,timeout=35,check=True)
    with Image.open(BytesIO(proc.stdout)) as img:
        return ImageOps.exif_transpose(img).convert("RGB")


@dataclass
class VideoShot:
    source: dict
    file: Path
    still: Image.Image
    description: str
    duration: float
    signature: int


def pick_moving_shots(topic: str) -> tuple[list[VideoShot],dict]:
    subject, terms=subject_search(topic)
    if not subject:
        raise RuntimeError("Topic has no filmable physical subject")
    checker=VisionReview()
    checker.maximum=MAX_REVIEWS
    library=[]
    seen=set()
    # Pexels is optional; Commons always works without any extra API secret.
    for phrase in terms[:5]:
        for gather in (pexels_sources, commons_sources):
            try:
                options=gather(phrase)
            except requests.RequestException as exc:
                LOG.warning("%s search unavailable (%s)",gather.__name__,str(exc)[:100])
                continue
            for o in options:
                key=(o["provider"],o["id"])
                if key in seen:
                    continue
                seen.add(key)
                overlap=len(stems(phrase) & stems(o["title"]))
                if o["provider"]=="Wikimedia Commons" and overlap<1:
                    continue
                library.append((int(o["provider"]=="Pexels"),overlap,o))
    library.sort(key=lambda v:(-v[0],-v[1]))
    report={"topic":topic,"searches":terms,"candidates":len(library),
            "videos_examined":[],"video_policy":"real-moving-licensed-footage-only"}
    LOG.info("Moving-video search found %d candidate video files",len(library))
    if not library:
        raise RuntimeError("No compatible Commons video results. Add free PEXELS_API_KEY or try a footage-rich topic.")

    picked=[]
    MEDIA.mkdir(exist_ok=True)
    for _priority,overlap,src in library[:55]:
        if len(picked)>=CLIPS or checker.calls>=checker.maximum:
            break
        temp=MEDIA/"candidate_video.part"
        if not download_clip(src,temp):
            continue
        try:
            media=probe_movie(temp)
            if not (5<=media["duration"]<=180 and
                    media["width"]>=480 and media["height"]>=320):
                continue
            frame=still_from_clip(temp,min(media["duration"]*.35,4))
            sig=perceptual_hash(frame)
            if any((sig ^ prior.signature).bit_count()<8 for prior in picked):
                continue
            # We only use authentic moving clips and inspect a real frame from
            # the actual downloaded source rather than the source's filename.
            verdict=checker.evaluate(
                frame,subject,
                f"Moving documentary B-roll for a science video about '{topic}'. "
                f"Must visually depict a genuine {subject} and be from a live camera, "
                "not CGI, a slide, poster, diagram, 3D simulation or illustration.",
                src["title"]
            )
            report["videos_examined"].append({
                "title":src["title"],"provider":src["provider"],
                "accepted":verdict["approve"],"reason":verdict["reason"]
            })
            if not verdict["approve"]:
                continue
            permanent=MEDIA/f"video_scene_{len(picked)+1:02d}{'.webm' if src['mime']=='video/webm' else '.mp4'}" if src["provider"]=="Wikimedia Commons" else MEDIA/f"video_scene_{len(picked)+1:02d}.mp4"
            temp.replace(permanent)
            src=dict(src,vision_approved=True,vision_subject=verdict["depicts"],
                     vision_explanation=verdict["reason"],title_overlap_terms=overlap)
            picked.append(VideoShot(src,permanent,frame,verdict["depicts"],
                                    media["duration"],sig))
            LOG.info("ACCEPTED moving scene %d/%d: %s (%0.1fs)",
                     len(picked),CLIPS,src["title"][:70],media["duration"])
        except (ValueError,subprocess.SubprocessError,OSError,RuntimeError) as exc:
            if isinstance(exc, RuntimeError):
                raise  # Quota-related and nonrecoverable review failures
            LOG.warning("Skipping video: %s",str(exc)[:100])
        finally:
            temp.unlink(missing_ok=True)
    report["vision_calls"]=checker.calls
    report["selected_videos"]=len(picked)
    PREPARED.mkdir(exist_ok=True)
    (PREPARED/"selection_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    if len(picked)<MIN_CLIPS:
        raise RuntimeError(f"Only {len(picked)} verified moving clips; require at least {MIN_CLIPS}. "
                           "No slideshow fallback. Free Pexels key can improve video coverage.")
    return picked,report


def prepare(topic: str):
    PREPARED.mkdir(exist_ok=True)
    MEDIA.mkdir(exist_ok=True)
    settings=Settings.from_env()
    shots,report=pick_moving_shots(topic)
    script_shots=[Shot(shot.source,shot.still,shot.description,shot.signature) for shot in shots]
    script=write_visual_script(topic,script_shots,settings)
    credits=[]
    rows=[]
    for i,(shot,scene) in enumerate(zip(shots,script.scenes)):
        token=f"facelessscene{chr(97+i)}"
        # Real frame provides a silent audio-render placeholder. Actual final
        # footage comes from the moving source in a separate edit stage.
        image_path=MEDIA/f"{token}_real_frame.jpg"
        full_frame_photo(shot.still).save(image_path,format="JPEG",quality=91)
        scene.search_query=token
        src=shot.source
        rows.append({"index":i,"kind":"real-moving-video",
                     "provider":src["provider"],"clip":str(shot.file),
                     "asset":str(image_path),"duration":shot.duration,
                     "source":src,"query":shot.description})
        credit=f'Clip {i+1}: {src["artist"]}, {src["title"]}, {src["license"]}, {src["page"]}'
        if credit not in credits:
            credits.append(credit)
    if credits:
        script.description+="\n\nVideo credits:\n"+"\n".join(credits)
    if any(shot.source["provider"]=="Pexels" for shot in shots):
        script.description+="\n\nVideos provided by Pexels: https://www.pexels.com"
    (PREPARED/"script.json").write_text(
        json.dumps(script.to_dict(),indent=2,ensure_ascii=False),encoding="utf-8")
    (PREPARED/"motion_manifest.json").write_text(json.dumps({
        "topic":topic,"source":"real-moving-footage-only",
        "storyboard_grounded":True,"scenes":rows,"vision_calls":report["vision_calls"]
    },indent=2,ensure_ascii=False),encoding="utf-8")
    print(f"MOTION READY: {len(rows)} verified real video sources; "
          f"Gemini-reviewed {report['vision_calls']} candidates; "
          f"{len(script.narration.split())} narration words")


if __name__=="__main__":
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv)<2:
        raise SystemExit("Usage: prepare_motion.py <filmed subject>")
    prepare(" ".join(sys.argv[1:]))

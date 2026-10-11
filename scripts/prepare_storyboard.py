#!/usr/bin/env python3
"""Build a science Short around verified real documentary images.

V5: VISUALS FIRST, WORDS SECOND.
No SVG, simulated shots, original diagrams or drawings are ever generated.
Wikimedia file license is checked and each photo is inspected with Gemini. Then
Gemini writes a documentary script in the EXACT order of those verified shots.
This avoids the former failure of trying to find a picture for an over-specific
hallucinated science line.
"""
from __future__ import annotations

from collections import Counter
import json
import logging
import os
from pathlib import Path
import re
import sys
import time
from dataclasses import dataclass

from PIL import Image, ImageOps

from purffle_shorts.config import Settings
from purffle_shorts.llm import LLM
from purffle_shorts.script import SCRIPT_SCHEMA, normalize

from prepare_content import (
    candidates, get_photo, VisionReview, stems, full_frame_photo,
    PREPARED, MEDIA, BAD_TITLE,
)

LOG = logging.getLogger("faceless.storyboard")
SCENE_COUNT = 6
MAX_IMAGE_REVIEWS = 15
# These search terms specify physical subjects with widely documented real photos.
# Avoid impossible "lightning air expands at 30,000 C" or microscopic CGI.
PHOTO_TOPICS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("rainbow", ("rainbow landscape", "rainbow sky", "double rainbow", "rainbow after rain")),
    ("lightning", ("lightning strike", "lightning storm", "lightning sky", "thunderstorm lightning")),
    ("volcano", ("volcano eruption", "lava flow", "volcano crater", "volcano ash cloud")),
    ("aurora", ("northern lights aurora", "aurora borealis", "aurora night sky")),
    ("northern lights", ("aurora borealis", "northern lights sky", "aurora photograph")),
    ("glacier", ("glacier ice", "glacier valley", "glacier mountain", "glacier ice front")),
    ("ocean wave", ("ocean waves", "breaking ocean waves", "coastal waves")),
    ("coral", ("coral reef underwater", "coral reef fish", "corals underwater")),
    ("hummingbird", ("hummingbird flower", "hummingbird flying", "hummingbird wings")),
    ("penguin", ("penguins colony", "penguin antarctica", "penguins on ice")),
    ("waterfall", ("waterfall river", "waterfall mountain", "waterfall landscape")),
    ("eclipse", ("solar eclipse", "eclipse totality", "solar eclipse photograph")),
    ("moon", ("moon night sky", "moon telescope photograph", "moon phases")),
    ("cloud", ("clouds thunderstorm", "cumulonimbus clouds", "storm clouds")),
    ("snowflake", ("snowflakes macro photography", "snowflakes", "snow crystals")),
    ("bees", ("bee flower", "honeybee flower", "bees collecting pollen")),
    ("hail", ("hailstones", "hail on ground", "hailstorm", "hail ice")),
    ("flamingo", ("flamingos", "flamingo bird water", "flamingo flock")),
    ("fog", ("fog over lake", "fog forest", "morning fog")),
    ("mushroom", ("wild mushroom", "mushroom forest", "mushroom spores")),
    ("dolphin", ("dolphins ocean", "dolphin pod", "dolphins swimming")),
    ("sand dune", ("sand dunes desert", "dunes Sahara", "desert dunes")),
    ("geysers", ("geyser eruption", "geyser hot water")),
    ("geyser", ("geyser eruption", "geyser hot water")),
    ("iceberg", ("icebergs", "iceberg ocean", "iceberg antarctica")),
    ("sunset", ("sunset sky", "red sunset", "sunset clouds")),
)


@dataclass
class Shot:
    source: dict
    image: Image.Image
    description: str
    hash64: int


def subject_search(topic: str) -> tuple[str, list[str]]:
    lower=topic.casefold()
    for trigger, queries in PHOTO_TOPICS:
        if trigger in lower:
            subject=trigger
            return subject, list(queries)
    # Generic topics can proceed only if Wikimedia offers enough honest photos.
    tokens=[w for w in re.findall(r"[a-z]{4,}",lower)
            if w not in {"what","does","from","when","where","have","been","with","that","this",
                         "much","into","during","because","forms","produces","makes","which"}]
    return " ".join(tokens[:2]), [" ".join(tokens[:3]), " ".join(tokens[:2])]


def perceptual_hash(img: Image.Image) -> int:
    small=img.convert("L").resize((8,8), Image.Resampling.BILINEAR)
    pixels=list(small.getdata())
    average=sum(pixels)/64
    return sum(1<<i for i,p in enumerate(pixels) if p>average)


def too_similar(candidate: int, shots: list[Shot]) -> bool:
    return any((candidate ^ shot.hash64).bit_count()<7 for shot in shots)


def choose_shots(topic: str, settings: Settings) -> tuple[list[Shot], dict]:
    subject,queries=subject_search(topic)
    if not subject:
        raise RuntimeError("No concrete physical topic for real-world photography")
    checker=VisionReview()
    checker.maximum=MAX_IMAGE_REVIEWS
    seen_pages=set()
    shots:list[Shot]=[]
    audit={"topic":topic,"photo_subject":subject,"search_terms":queries,
           "reviews":[],"visual_policy":"real-camera-photos-only",
           "max_reviews":MAX_IMAGE_REVIEWS}
    # Select from several focused search phrases, then sort to avoid six near-
    # identical photos from the first batch.
    pool: list[tuple[int, dict, str]]=[]
    for phrase in queries:
        try:
            for source in candidates(phrase):
                page=source.get("page","")
                if not page or page in seen_pages:
                    continue
                seen_pages.add(page)
                intersect=len(stems(source.get("title","")) & stems(phrase))
                if intersect>=1:
                    pool.append((intersect,source,phrase))
        except Exception as exc:
            LOG.warning("Commons query %r failed (%s)", phrase, str(exc)[:150])
    if not pool:
        raise RuntimeError(f"No freely licensed camera photographs found for {subject!r}")
    # Prioritize matching titles, favor alternate queries and unique compositions.
    pool.sort(key=lambda entry:(-entry[0],len(entry[1].get("title",""))))
    LOG.info("Commons candidates: %d for %s",len(pool),subject)
    for overlap, source,phrase in pool:
        if len(shots)>=SCENE_COUNT or checker.calls>=checker.maximum:
            break
        try:
            img=get_photo(source)
            h=perceptual_hash(img)
            if too_similar(h,shots):
                audit["reviews"].append({"title":source["title"],"approved":False,
                                         "reason":"visually near-duplicate"})
                continue
            # Image review is subject-level: don't claim it proves every fact.
            review=checker.evaluate(
                img,subject,
                f"An educational documentary about {topic}. "
                f"This should be a real photograph of the physical subject '{subject}', "
                "not unrelated people, graphics, commercial objects, illustrations or fiction.",
                source["title"]
            )
            audit["reviews"].append({"title":source["title"],"approved":review["approve"],
                                     "reason":review["reason"]})
            if not review["approve"]:
                continue
            source=dict(source,title_overlap_terms=overlap,
                        vision_approved=True,
                        vision_subject=review["depicts"],
                        vision_explanation=review["reason"])
            shots.append(Shot(source, img, review["depicts"], h))
            LOG.info("VERIFIED PHOTO %d/%d: %s, depicts %s",
                     len(shots),SCENE_COUNT,source["title"][:65],review["depicts"][:100])
        except RuntimeError:
            raise  # quota errors must stop, never silently bypass checking
        except Exception as exc:
            audit["reviews"].append({"title":source.get("title"),"approved":False,
                                     "reason":"download/review unavailable"})
            LOG.warning("Photo skipped: %s",str(exc)[:120])
    audit["vision_requests"]=checker.calls
    audit["selected"]=len(shots)
    (PREPARED/"selection_report.json").write_text(
        json.dumps(audit,indent=2,ensure_ascii=False),encoding="utf-8")
    if len(shots)!=SCENE_COUNT:
        raise RuntimeError(
            f"Only {len(shots)} of {SCENE_COUNT} authentic, distinct photos approved "
            f"within {checker.calls} Gemini vision calls. No generated-art fallback. "
            "Choose another photo-rich science topic."
        )
    return shots,audit


def write_visual_script(topic: str, shots: list[Shot], settings: Settings):
    llm=LLM(settings)
    shots_description="\n".join(
        f"SCENE {idx+1}: Photograph visibly depicts: {shot.description!r}. "
        f"Filename: {shot.source['title']!r}."
        for idx,shot in enumerate(shots)
    )
    system=(
        "You are a scientifically careful documentary producer writing an authentic 35-second "
        "vertical video for an audience that wants to understand the real world. "
        "You have exactly six REAL PHOTOGRAPHS, already selected and verified. "
        "Write a naturally spoken script scene-by-scene matching THOSE ACTUAL PHOTOS IN ORDER. "
        "No invented claims, misleading image-to-claim matches, fake quotes or dramatic false facts. "
        "Don't pretend the photo shows something it does not. "
        "Return one valid JSON object following the provided schema."
    )
    prompt=(
        f"Topic: {topic}\n\nVerified visual storyboard (fixed order):\n{shots_description}\n\n"
        f"Rules: EXACTLY {len(shots)} scenes in EXACTLY the listed order. "
        "First line must hook immediately without a question like 'did you know'. "
        "One connected coherent scientific explanation, not a list of random photo descriptions. "
        "Across six scenes write approximately 85-104 total narrated words. "
        "Each narration should be 10-21 natural spoken words. "
        "Use correct measurements and clear comparisons if numerical facts are needed. "
        "No 'like and subscribe', no false emotional urgency, no misleading impossible visual. "
        "Last scene must deliver a satisfying conclusion, not filler. "
        "Each scene's search_query must describe what the associated photograph ACTUALLY shows, "
        "and image_prompt must also describe the verified image; no instructions to create artwork. "
        "Six chronological story beats: hook, context, mechanism, mechanism, consequence, payoff. "
        "Title should be accurate, specific, and shorter than 55 characters. "
        "Description should summarize the true science and invite a relevant viewer question. "
        'JSON fields: "topic", "title", "hook_text", "cast", "scenes" '
        '(array of {"speaker":"A","narration","search_query","image_prompt"}), '
        '"description","hashtags","tags","category". Category science.'
    )
    data=llm.complete_json(system,prompt,SCRIPT_SCHEMA,max_tokens=4500)
    script=normalize(data,topic,"explainer","en")
    if len(script.scenes)!=len(shots):
        raise RuntimeError("Gemini changed the approved storyboard scene count: rejected")
    nwords=len(script.narration.split())
    if not 70<=nwords<=125:
        raise RuntimeError(f"Gemini returned {nwords} words; require 70-125")
    for idx,scene in enumerate(script.scenes):
        n=len(scene.narration.split())
        if not 8<=n<=25:
            raise RuntimeError(f"Scene {idx+1} has {n} words; require 8-25")
    return script


def run(topic: str) -> None:
    PREPARED.mkdir(parents=True,exist_ok=True)
    MEDIA.mkdir(parents=True,exist_ok=True)
    settings=Settings.from_env()
    shots,audit=choose_shots(topic,settings)
    script=write_visual_script(topic,shots,settings)
    entries=[]
    credits=[]
    for i,(shot,scene) in enumerate(zip(shots,script.scenes)):
        token=f"facelessscene{chr(97+i)}"
        file=MEDIA/f"{token}_photo.jpg"
        full_frame_photo(shot.image).save(file,format="JPEG",quality=92,optimize=True)
        scene.search_query=token
        src=shot.source
        entries.append({"index":i,"query":shot.description,
                        "kind":"wikimedia-photo","match":"direct",
                        "asset":str(file),"source":src})
        if "by" in src["license"].lower():
            attribution=(f'Photo {i+1}: {src["artist"]}, {src["title"]}, '
                         f'{src["license"]} ({src["license_url"]}), {src["page"]}')
            if attribution not in credits:
                credits.append(attribution)
    if credits:
        script.description+="\n\nPhoto credits:\n"+"\n".join(credits)
    (PREPARED/"script.json").write_text(
        json.dumps(script.to_dict(),indent=2,ensure_ascii=False),encoding="utf-8")
    (PREPARED/"visual_manifest.json").write_text(
        json.dumps({"topic":topic,"visual_policy":"licensed-real-photography-only",
                    "unique_photos":len(shots),"storyboard_grounded":True,
                    "scene_order_verified":True,"scenes":entries},indent=2,ensure_ascii=False),
        encoding="utf-8"
    )
    print(f"READY: {len(shots)} Gemini-verified real photos, script grounded to each photo, "
          f"{len(script.narration.split())} words, {audit['vision_requests']} vision checks")


if __name__=="__main__":
    logging.basicConfig(level=logging.INFO)
    topic=" ".join(sys.argv[1:]).strip()
    if not topic:
        raise SystemExit("Specify a visual documentary topic")
    run(topic)

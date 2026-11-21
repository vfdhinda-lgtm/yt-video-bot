"""Writes an original, engaging script with the free Google Gemini API."""
import json
import os
import re
import time

import requests

from bot import config

SCRIPT_PROMPT = """You are the head writer of a top US YouTube channel that makes immersive, second-person
history videos in the format "Your Entire Life as ...". Viewers stay because every scene has a vivid
detail, a surprising true fact, or emotion.

Write a COMPLETELY ORIGINAL video for this title: "{title}"

STORY RULES
- Scene 1 is a HOOK (about 25-40 words): a shocking true fact or tense moment that makes people keep
  watching. Then the life starts at birth.
- Second person, present tense ("You are born..."). One life in order: birth, childhood, coming of age,
  work, love/family, danger, old age, death. End with a short emotional closing line.
- Historically accurate, sensory details (smell, sound, food, weather), real surprising facts,
  simple American English, warm documentary tone. Vary sentence length. No lists or headings.
- Total narration: about {words} words, split into about {scenes} scenes of 30-60 words each.

CHARACTERS (very important for consistent faces)
- Create a "characters" list (max 4: the main character "YOU" plus important people like mother,
  father, spouse, master). For each give a fixed "face" description that never changes:
  face shape, skin tone, eye color and shape, nose, eyebrows, hair color/texture, one distinctive mark.
- In every image_prompt, refer to characters ONLY by their id in square brackets, e.g. [YOU], [MOTHER],
  and say their age and clothing in that scene. Never re-describe their face yourself.

SCENE FIELDS
- "chapter": a short on-screen label ONLY on the first scene of a new life stage, like "Birth",
  "Age 7", "Age 16", "Age 25", "Age 40", "Old Age", "The End". Otherwise "".
  The hook scene has chapter "".
- "narration": the voiceover text.
- "image_prompt": one clear visual moment: setting, time period, action, camera angle, lighting.
  Mostly one or two characters per image. No text, letters or logos.
- "characters": list of character ids in the image.
- "sfx": 1-3 word sound effect to search for (e.g. "crackling fire", "crowd cheering", "rain",
  "sword clash", "baby crying", "horse gallop", "market crowd"), or "" if none.

Return ONLY valid JSON in exactly this shape:
{{
  "title": "{title}",
  "description": "150-250 word YouTube description, SEO friendly, ends with 3 hashtags",
  "tags": ["15 short SEO tags"],
  "thumbnail_text": "max 4 punchy words",
  "thumbnail_prompt": "dramatic close-up of [YOU] at the most intense moment of the story, no text",
  "characters": [{{"id": "YOU", "name": "...", "face": "..."}}],
  "scenes": [{{"chapter": "", "narration": "...", "image_prompt": "...", "characters": ["YOU"], "sfx": "..."}}]
}}
"""

TOPIC_PROMPT = """Suggest ONE new YouTube video title in the exact format
"Your Entire Life as a/an <historical person type>" (e.g. a Roman gladiator, a Viking farmer,
a medieval peasant, an Egyptian pyramid builder). It must interest a US audience and be historically rich.
Do NOT use any of these already-made titles:
{done}
Return only the title text, nothing else."""


def gemini(prompt, json_mode=False):
    key = os.environ["GEMINI_API_KEY"]
    model = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.9}}
    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"
    for attempt in range(6):
        r = requests.post(url, params={"key": key}, json=body, timeout=300)
        if r.status_code == 200:
            parts = r.json()["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts)
        if r.status_code in (429, 500, 502, 503, 504):
            wait = 30 * (attempt + 1)
            print(f"Gemini busy ({r.status_code}), waiting {wait}s...")
            time.sleep(wait)
            continue
        raise RuntimeError(f"Gemini error {r.status_code}: {r.text[:500]}")
    raise RuntimeError("Gemini failed after several tries")


def new_topic(done_titles):
    done = "\n".join(f"- {t}" for t in done_titles[-200:]) or "- (none yet)"
    return gemini(TOPIC_PROMPT.format(done=done)).strip().strip('"').splitlines()[0].strip('"')


def _parse_json(text):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    return json.loads(text)


def _clean(data, title):
    chars = {}
    for c in data.get("characters", [])[:4]:
        cid = str(c.get("id", "")).strip().upper()
        if cid and c.get("face"):
            chars[cid] = {"id": cid, "name": c.get("name", cid), "face": c["face"].strip()}
    data["characters"] = list(chars.values())
    scenes = []
    for s in data.get("scenes", []):
        if not str(s.get("narration", "")).strip() or not str(s.get("image_prompt", "")).strip():
            continue
        s["chapter"] = str(s.get("chapter") or "").strip()
        s["sfx"] = str(s.get("sfx") or "").strip()
        s["characters"] = [str(c).upper() for c in (s.get("characters") or []) if str(c).upper() in chars]
        scenes.append(s)
    if len(scenes) < 10:
        raise ValueError("too few scenes")
    data["scenes"] = scenes
    data["title"] = title
    return data


def write_script(title):
    prompt = SCRIPT_PROMPT.format(title=title, words=config.get("words"), scenes=config.get("scenes"))
    for attempt in range(3):
        try:
            return _clean(_parse_json(gemini(prompt, json_mode=True)), title)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
            print(f"Script attempt {attempt + 1} was not usable ({e}), retrying...")
    raise RuntimeError("Could not get a usable script from Gemini")

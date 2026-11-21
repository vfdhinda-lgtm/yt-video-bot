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


def _gemini_once(model, prompt, json_mode, timeout):
    """One call to one Gemini model. Returns text, or raises _Skip / _Busy."""
    key = os.environ["GEMINI_API_KEY"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    cfg = {"temperature": 0.9, "thinkingConfig": {"thinkingLevel": "low"}}
    if json_mode:
        cfg["responseMimeType"] = "application/json"
    for _ in range(2):
        try:
            r = requests.post(url, headers={"x-goog-api-key": key}, timeout=timeout,
                              json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": cfg})
        except (requests.Timeout, requests.ConnectionError) as e:
            raise _Busy(f"{model}: {type(e).__name__}")
        if r.status_code == 200:
            parts = r.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
            if text.strip():
                return text
            raise _Busy(f"{model}: empty answer")
        if r.status_code == 400 and "thinking" in r.text.lower() and "thinkingConfig" in cfg:
            cfg.pop("thinkingConfig")  # this model does not support thinkingLevel
            continue
        if r.status_code in (400, 403, 404):
            raise _Skip(f"{model}: {r.status_code} {r.text[:150]}")
        raise _Busy(f"{model}: {r.status_code}")
    raise _Skip(f"{model}: rejected settings")


def _cloudflare_llm(prompt):
    """Backup writer: Cloudflare Workers AI (uses the same Cloudflare keys as the images)."""
    acc, tok = os.environ.get("CF_ACCOUNT_ID"), os.environ.get("CF_API_TOKEN")
    if not (acc and tok):
        raise _Skip("Cloudflare keys not set")
    model = os.environ.get("CF_TEXT_MODEL", "@cf/meta/llama-3.3-70b-instruct-fp8-fast")
    r = requests.post(f"https://api.cloudflare.com/client/v4/accounts/{acc}/ai/run/{model}",
                      headers={"Authorization": f"Bearer {tok}"}, timeout=600,
                      json={"messages": [{"role": "user", "content": prompt}], "max_tokens": 8000, "temperature": 0.8})
    if r.status_code != 200:
        raise _Busy(f"Cloudflare {r.status_code}: {r.text[:150]}")
    res = r.json().get("result", {}).get("response", "")
    return json.dumps(res) if isinstance(res, (dict, list)) else str(res)


class _Busy(Exception):
    pass


class _Skip(Exception):
    pass


def gemini(prompt, json_mode=False):
    """Ask AI. Tries several Gemini models (when one is overloaded, the next one usually works),
    then Cloudflare as a backup. Repeats the whole round 3 times with a pause."""
    first = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
    models = [m for m in dict.fromkeys([first, "gemini-flash-latest", "gemini-3.8-flash-lite", "gemini-flash-lite-latest"]) if m]
    errors = []
    for round_no in range(3):
        for m in models:
            try:
                return _gemini_once(m, prompt, json_mode, timeout=420)
            except (_Busy, _Skip) as e:
                errors.append(str(e))
                print(f"AI not available: {e}")
        try:
            print("Trying Cloudflare AI as backup...")
            return _cloudflare_llm(prompt)
        except (_Busy, _Skip) as e:
            errors.append(str(e))
            print(f"Backup not available: {e}")
        if round_no < 2:
            print("All AI busy, waiting 2 minutes...")
            time.sleep(120)
    raise RuntimeError("All AI models busy. Last errors: " + " | ".join(errors[-4:]))


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

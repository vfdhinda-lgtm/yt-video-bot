"""Free AI images with FLUX (Cloudflare Workers AI if keys are set, otherwise Pollinations.ai).
Characters keep the same face: each one has a fixed face description and a fixed seed."""
import base64
import io
import os
import re
import time
import urllib.parse
import zlib

import requests
from PIL import Image

from bot import config

W, H = 1920, 1080


def _fit(img_bytes, path, size=(W, H)):
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    tw, th = size
    scale = max(tw / img.width, th / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    left, top = (img.width - tw) // 2, (img.height - th) // 3  # keep heads (upper part) in frame
    img.crop((left, top, left + tw, top + th)).save(path, "JPEG", quality=92)


_cf_mode = [0]  # which request shape Cloudflare accepted last time


def _cloudflare(prompt, seed):
    acc = os.environ["CF_ACCOUNT_ID"]
    url = f"https://api.cloudflare.com/client/v4/accounts/{acc}/ai/run/@cf/black-forest-labs/flux-1-schnell"
    shapes = [{"prompt": prompt[:2000], "steps": 8, "seed": seed},   # full
              {"prompt": prompt[:2000], "steps": 8},                 # without seed
              {"prompt": prompt[:1000]}]                              # minimal
    last = ""
    for i in range(_cf_mode[0], len(shapes)):
        r = requests.post(url, headers={"Authorization": f"Bearer {os.environ['CF_API_TOKEN']}"}, json=shapes[i], timeout=180)
        if r.status_code == 200:
            _cf_mode[0] = i
            return base64.b64decode(r.json()["result"]["image"])
        last = f"Cloudflare {r.status_code}: {r.text[:300]}"
        if r.status_code != 400:
            break
    raise RuntimeError(last)


def _pollinations(prompt, seed):
    q = urllib.parse.quote(prompt[:1500])
    url = (f"https://image.pollinations.ai/prompt/{q}?width={W}&height={H}"
           f"&seed={seed}&nologo=true&model=flux")
    headers = {}
    if os.environ.get("POLLINATIONS_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['POLLINATIONS_TOKEN']}"
    r = requests.get(url, headers=headers, timeout=240)
    r.raise_for_status()
    if not r.headers.get("content-type", "").startswith("image"):
        raise RuntimeError("Pollinations did not return an image")
    return r.content


def build_prompt(image_prompt, characters):
    """Replace [ID] with the character's fixed face card."""
    cmap = {c["id"]: c for c in characters}

    def rep(m):
        c = cmap.get(m.group(1).upper())
        return f"{c['name']} ({c['face']})" if c else m.group(1)

    text = re.sub(r"\[([A-Za-z_ ]+)\]", rep, image_prompt)
    return (f"{config.style_text()}. {text}. Same art style in every image. "
            f"No text, no letters, no watermark, no captions.")


def scene_seed(scene, base_seed, index):
    chars = scene.get("characters") or []
    if len(chars) == 1:  # one main person -> use that person's fixed seed
        return base_seed + zlib.crc32(chars[0].encode()) % 100000
    return base_seed + 500000 + index


def make_image(prompt, path, seed, size=(W, H)):
    """Cloudflare first (if keys are set); if it keeps failing, Pollinations.ai as backup."""
    services = ([_cloudflare] if os.environ.get("CF_ACCOUNT_ID") and os.environ.get("CF_API_TOKEN") else []) + [_pollinations]
    for service in services:
        for attempt in range(3):
            try:
                _fit(service(prompt, seed), path, size)
                return True
            except Exception as e:  # noqa: BLE001
                wait = 10 * (attempt + 1)
                print(f"  {service.__name__.strip('_')} try {attempt + 1} failed ({str(e)[:300]}); waiting {wait}s")
                time.sleep(wait)
    return False


def make_all(meta, folder, base_seed, progress=None):
    scenes, chars = meta["scenes"], meta.get("characters", [])
    paths, last_good, failed = [], None, 0
    delay = float(os.environ.get("IMAGE_DELAY", "4"))
    for i, s in enumerate(scenes):
        p = os.path.join(folder, f"img_{i:03d}.jpg")
        print(f"Image {i + 1}/{len(scenes)}")
        if progress and i % 5 == 0:
            progress(f"Images {i + 1}/{len(scenes)}")
        if make_image(build_prompt(s["image_prompt"], chars), p, scene_seed(s, base_seed, i)):
            last_good = p
        else:
            failed += 1
            if last_good is None:
                raise RuntimeError("First image could not be made. Check the image service.")
            p = last_good
        paths.append(p)
        time.sleep(delay)
    if failed > len(scenes) * 0.3:
        raise RuntimeError(f"{failed} images failed; stopping so a bad video is not uploaded.")
    return paths

"""Free sound effects from Freesound.org (only CC0 = free to use, no credit needed)."""
import os
import re

import requests

_cache = {}


def get(query, folder):
    """Returns a local mp3 path for the sound, or None."""
    key = os.environ.get("FREESOUND_API_KEY")
    query = (query or "").strip().lower()
    if not key or not query:
        return None
    if query in _cache:
        return _cache[query]
    path = None
    try:
        r = requests.get("https://freesound.org/apiv2/search/text/", timeout=30, params={
            "query": query,
            "filter": 'license:"Creative Commons 0" duration:[2 TO 30]',
            "fields": "id,name,previews,duration",
            "sort": "rating_desc",
            "page_size": 5,
            "token": key,
        })
        r.raise_for_status()
        for res in r.json().get("results", []):
            url = res.get("previews", {}).get("preview-hq-mp3")
            if not url:
                continue
            a = requests.get(url, timeout=60)
            if a.ok and len(a.content) > 2000:
                path = os.path.join(folder, "sfx_" + re.sub(r"[^a-z0-9]+", "_", query) + ".mp3")
                with open(path, "wb") as f:
                    f.write(a.content)
                break
    except Exception as e:  # noqa: BLE001
        print(f"  sound effect '{query}' skipped ({e})")
    _cache[query] = path
    return path

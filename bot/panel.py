"""Talks to the admin panel on your website (optional). Without PANEL_URL the bot uses topics.txt."""
import os

import requests

URL = os.environ.get("PANEL_URL", "").rstrip("/")
KEY = os.environ.get("BOT_KEY", "")


def enabled():
    return bool(URL and KEY)


def _api(method, action, **data):
    url = f"{URL}/api.php"
    params = {"action": action, "key": KEY}
    for attempt in range(3):
        try:
            if method == "GET":
                r = requests.get(url, params={**params, **data}, timeout=30)
            else:
                r = requests.post(url, params=params, data=data, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            print(f"  panel {action} try {attempt + 1} failed: {e}")
    return {}


def next_job(trigger):
    return _api("GET", "next", trigger=trigger)


def update(job_id, **fields):
    if enabled() and job_id:
        _api("POST", "update", job_id=job_id, **{k: str(v)[:3000] for k, v in fields.items()})


def download_music(folder="music"):
    if not enabled():
        return
    files = _api("GET", "music").get("files", [])
    os.makedirs(folder, exist_ok=True)
    for f in files:
        dest = os.path.join(folder, os.path.basename(f["name"]))
        if os.path.exists(dest):
            continue
        try:
            r = requests.get(f["url"], timeout=120)
            r.raise_for_status()
            with open(dest, "wb") as fh:
                fh.write(r.content)
            print(f"Music downloaded: {f['name']}")
        except Exception as e:  # noqa: BLE001
            print(f"  music {f['name']} skipped: {e}")

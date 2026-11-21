"""Uploads the video + thumbnail to YouTube with the free YouTube Data API."""
import datetime as dt
import os

from bot import config

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


def _client():
    creds = Credentials(
        None,
        refresh_token=os.environ["YT_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YT_CLIENT_ID"],
        client_secret=os.environ["YT_CLIENT_SECRET"],
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def _publish_time():
    """Next PUBLISH_HOUR_UTC (default 15 UTC = 10 AM US Eastern) as RFC3339, or None."""
    hour = config.get("publish_hour_utc").strip()
    if not hour:
        return None
    now = dt.datetime.now(dt.timezone.utc)
    t = now.replace(hour=int(hour), minute=0, second=0, microsecond=0)
    if t <= now + dt.timedelta(minutes=20):
        t += dt.timedelta(days=1)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def upload(video_path, thumb_path, meta, progress=None):
    yt = _client()
    tags, total = [], 0
    for t in meta.get("tags", []):
        t = str(t).strip().replace("<", "").replace(">", "")
        if t and total + len(t) + 2 < 480:
            tags.append(t)
            total += len(t) + 2

    status = {"selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}
    when = _publish_time() if (config.get("privacy") or "public") == "public" else None
    if when:
        status.update(privacyStatus="private", publishAt=when)
    else:
        status["privacyStatus"] = config.get("privacy") or "public"

    body = {
        "snippet": {
            "title": meta["title"][:100],
            "description": meta.get("description", "")[:4900].replace("<", "").replace(">", ""),
            "tags": tags,
            "categoryId": "27",  # Education
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en-US",
        },
        "status": status,
    }
    req = yt.videos().insert(
        part="snippet,status", body=body,
        media_body=MediaFileUpload(video_path, mimetype="video/mp4",
                                   chunksize=16 * 1024 * 1024, resumable=True),
    )
    resp = None
    while resp is None:
        st, resp = req.next_chunk()
        if st:
            print(f"Uploading... {int(st.progress() * 100)}%")
            if progress:
                progress(f"Uploading {int(st.progress() * 100)}%")
    vid = resp["id"]
    print(f"Uploaded: https://youtu.be/{vid}  (publish: {when or status['privacyStatus']})")
    try:
        yt.thumbnails().set(videoId=vid,
                            media_body=MediaFileUpload(thumb_path, mimetype="image/jpeg")).execute()
        print("Thumbnail set")
    except Exception as e:  # noqa: BLE001
        print(f"Thumbnail not set (verify your channel phone number to allow it): {e}")
    return vid

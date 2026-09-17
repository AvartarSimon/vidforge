"""YouTube Data API v3: video + thumbnail + captions in one command.

Setup (once):
  1. https://console.cloud.google.com -> new project -> enable "YouTube Data API v3"
  2. Credentials -> OAuth client ID -> Desktop app -> download JSON
  3. save it as  ~/.vidforge/client_secret.json   (or set YOUTUBE_CLIENT_SECRET=<path>)
  4. pip install "vidforge[youtube]"   (google-api-python-client, google-auth-oauthlib)
  First `vidforge upload` opens a browser for consent; the token is kept in ~/.vidforge/.

Facts that shape the defaults:
  * Quota: 10,000 units/day; videos.insert = 1,600, thumbnails.set = 50, captions.insert = 400
    -> about 5 uploads per day.
  * Videos uploaded by an OAuth app that has not passed Google's "YouTube API audit" are locked
    to PRIVATE. So the default here is private; publish (or schedule) from YouTube Studio.
  * Custom thumbnails need a phone-verified channel.
  * `build/youtube.json` remembers the video id: re-running updates metadata/thumbnail/captions
    instead of uploading twice.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from ..project import Project
from . import build_description

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.force-ssl"]
CONFIG_DIR = Path.home() / ".vidforge"


class YouTubeError(RuntimeError):
    pass


def _imports():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
        from googleapiclient.http import MediaFileUpload
    except ImportError:
        raise YouTubeError('YouTube libraries missing: pip install "google-api-python-client" "google-auth-oauthlib"'
                           ' (or: pip install -e ".[youtube]")') from None
    return Request, Credentials, InstalledAppFlow, build, HttpError, MediaFileUpload


def client():
    Request, Credentials, InstalledAppFlow, build, _, _ = _imports()
    CONFIG_DIR.mkdir(exist_ok=True)
    secret = Path(os.environ.get("YOUTUBE_CLIENT_SECRET", CONFIG_DIR / "client_secret.json"))
    token_path = CONFIG_DIR / "youtube_token.json"
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not secret.exists():
                raise YouTubeError(f"OAuth client secret not found: {secret}\n" + __doc__.split("Facts")[0])
            flow = InstalledAppFlow.from_client_secrets_file(str(secret), SCOPES)
            creds = flow.run_local_server(port=0, prompt="consent")
        token_path.write_text(creds.to_json(), encoding="utf-8")
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def upload(project: Project, *, privacy: str | None = None, publish_at: str | None = None,
           yt=None, log=print) -> dict:
    """Upload final.mp4 (+ thumbnail + captions). Returns the state dict written to build/youtube.json."""
    _, _, _, _, HttpError, MediaFileUpload = _imports()
    bd = project.build_dir
    video = bd / "final.mp4"
    if not video.exists():
        raise YouTubeError(f"{video} not found — run `vidforge build` first")
    state_path = bd / "youtube.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    yt = yt or client()
    cfg = project.youtube
    privacy = privacy or cfg.privacy

    snippet = {
        "title": (cfg.title or project.title)[:100],
        "description": build_description(project, bd),
        "tags": cfg.tags[:30],
        "categoryId": str(cfg.category_id),
        "defaultLanguage": project.language,
        "defaultAudioLanguage": project.language,
    }
    status = {"privacyStatus": privacy, "selfDeclaredMadeForKids": False,
              "containsSyntheticMedia": bool(cfg.disclosure.youtube_synthetic_flag)}
    if publish_at:
        status["privacyStatus"] = "private"          # YouTube requires private + publishAt
        status["publishAt"] = publish_at

    try:
        if state.get("video_id"):
            vid = state["video_id"]
            log(f"[youtube] updating metadata of existing video {vid}")
            yt.videos().update(part="snippet,status",
                               body={"id": vid, "snippet": snippet, "status": status}).execute()
        else:
            log(f"[youtube] uploading {video.name} ({video.stat().st_size / 1e6:.1f} MB) as {status['privacyStatus']}")
            media = MediaFileUpload(str(video), chunksize=8 * 1024 * 1024, resumable=True, mimetype="video/mp4")
            req = yt.videos().insert(part="snippet,status", body={"snippet": snippet, "status": status}, media_body=media)
            resp = None
            while resp is None:
                progress, resp = req.next_chunk()
                if progress:
                    log(f"[youtube]   {progress.progress() * 100:5.1f} %")
            vid = resp["id"]
            state["video_id"] = vid
            state_path.write_text(json.dumps(state, indent=1), encoding="utf-8")

        thumb = bd / "thumbnail.jpg"
        if thumb.exists():
            try:
                yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(str(thumb), mimetype="image/jpeg")).execute()
                state["thumbnail"] = True
            except HttpError as e:
                log(f"[youtube] thumbnail skipped: {_reason(e)} (custom thumbnails need a verified channel)")

        srt = bd / "final.srt"
        if srt.exists() and not state.get("caption_id"):
            body = {"snippet": {"videoId": vid, "language": project.language,
                                "name": cfg.caption_name or project.language.upper(), "isDraft": False}}
            cap = yt.captions().insert(part="snippet", body=body,
                                       media_body=MediaFileUpload(str(srt), mimetype="application/octet-stream")).execute()
            state["caption_id"] = cap["id"]

        if cfg.playlist_id and not state.get("in_playlist"):
            yt.playlistItems().insert(part="snippet", body={"snippet": {
                "playlistId": cfg.playlist_id, "resourceId": {"kind": "youtube#video", "videoId": vid}}}).execute()
            state["in_playlist"] = True
    except HttpError as e:
        raise YouTubeError(f"YouTube API error: {_reason(e)}") from None

    state["url"] = f"https://youtu.be/{vid}"
    state["uploaded_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    state_path.write_text(json.dumps(state, indent=1), encoding="utf-8")
    log(f"[youtube] done: {state['url']}  ({status['privacyStatus']}"
        + (f", publishAt {publish_at}" if publish_at else "") + ")")
    return state


def _reason(e) -> str:
    try:
        return json.loads(e.content)["error"]["errors"][0]["reason"]
    except Exception:  # noqa: BLE001
        return str(e)

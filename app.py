import os
import tempfile
from urllib.parse import quote

from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from functools import wraps
from werkzeug.utils import secure_filename

from supabase import create_client, Client
import cloudinary
from cloudinary import uploader


ALLOWED = {"mp3", "wav", "m4a", "flac", "ogg", "aac"}
COVER_ALLOWED = {"jpg", "jpeg", "png", "webp"}

# Cloudinary Free supports audio/video files up to 100 MB
MAX_MB = 100


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "replace-me")
app.config["MAX_CONTENT_LENGTH"] = MAX_MB * 1024 * 1024


# -----------------------------
# Supabase
# -----------------------------

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)


# -----------------------------
# Cloudinary
# -----------------------------

cloudinary.config(
    cloud_name=os.environ["CLOUDINARY_CLOUD_NAME"],
    api_key=os.environ["CLOUDINARY_API_KEY"],
    api_secret=os.environ["CLOUDINARY_API_SECRET"],
    secure=True
)


# -----------------------------
# Helpers
# -----------------------------

def ext_ok(name, allowed):
    return (
        "." in name
        and name.rsplit(".", 1)[1].lower() in allowed
    )


def admin_required(f):
    @wraps(f)
    def w(*args, **kwargs):
        if not session.get("admin"):
            return redirect(
                url_for("login", next=request.path)
            )
        return f(*args, **kwargs)

    return w


def normalize_beat(beat):
    """
    Keeps compatibility with the existing templates.
    """
    beat["cover"] = beat.get("cover_url")
    beat["filename"] = (
        beat.get("audio_url")
        or beat.get("filename")
        or ""
    )
    return beat


def get_beats():
    result = (
        supabase
        .table("beats")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )

    beats = result.data or []

    return [normalize_beat(b) for b in beats]


def attachment_url(url):
    """
    Converts a Cloudinary upload URL into a download URL.
    """
    if not url:
        return url

    if "/upload/" in url:
        return url.replace(
            "/upload/",
            "/upload/fl_attachment/",
            1
        )

    return url


# -----------------------------
# Global branding
# -----------------------------

@app.context_processor
def global_settings():

    result = (
        supabase
        .table("settings")
        .select("*")
        .eq("id", 1)
        .execute()
    )

    if result.data:
        site = result.data[0]
    else:
        site = {
            "artist_name": "YOUR ARTIST NAME",
            "tagline": "Instrumentals for your next record",
            "logo_text": "YOUR LOGO"
        }

    return {"site": site}


# -----------------------------
# Homepage
# -----------------------------

@app.route("/")
def index():

    q = request.args.get("q", "").strip()
    genre = request.args.get("genre", "").strip()

    all_beats = get_beats()

    genres = sorted({
        (b.get("genre") or "").strip()
        for b in all_beats
        if (b.get("genre") or "").strip()
    })

    beats = all_beats

    if q:
        ql = q.lower()

        beats = [
            b for b in beats

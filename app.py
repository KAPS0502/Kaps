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
            b for b in beats            if ql in (b.get("title") or "").lower()
            or ql in (b.get("genre") or "").lower()
            or ql in (b.get("key_name") or "").lower()
        ]

    if genre:
        beats = [
            b for b in beats
            if (b.get("genre") or "") == genre
        ]

    return render_template(
        "index.html",
        beats=beats,
        genres=genres,
        q=q,
        genre=genre
    )


@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        if request.form.get("password", "") == os.environ.get(
            "ADMIN_PASSWORD",
            "change-me"
        ):
            session["admin"] = True

            return redirect(
                request.args.get("next")
                or url_for("admin")
            )

        flash("Incorrect password.")

    return render_template("login.html")


@app.post("/logout")
def logout():

    session.clear()

    return redirect(url_for("index"))


@app.route("/admin")
@admin_required
def admin():

    beats = get_beats()

    return render_template(
        "admin.html",
        beats=beats
    )


@app.post("/settings")
@admin_required
def settings():

    artist_name = (
        request.form.get("artist_name", "").strip()
        or "YOUR ARTIST NAME"
    )

    tagline = request.form.get(
        "tagline",
        ""
    ).strip()

    logo_text = (
        request.form.get("logo_text", "").strip()
        or "YOUR LOGO"
    )

    supabase.table("settings").update({
        "artist_name": artist_name,
        "tagline": tagline,
        "logo_text": logo_text
    }).eq("id", 1).execute()

    flash("Brand settings saved.")

    return redirect(url_for("admin"))


@app.post("/upload")
@admin_required
def upload():

    title = request.form.get("title", "").strip()
    audio = request.files.get("audio")
    cover = request.files.get("cover")

    if not title or not audio or not audio.filename:
        flash("Title and audio file are required.")
        return redirect(url_for("admin"))

    if not ext_ok(audio.filename, ALLOWED):
        flash("Unsupported audio format.")
        return redirect(url_for("admin"))

    original_name = secure_filename(audio.filename)
    audio_ext = original_name.rsplit(".", 1)[1].lower()

    audio_temp = None
    cover_temp = None
    audio_result = None
    cover_result = None

    try:

        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix="." + audio_ext
        ) as temp_audio:
            audio_temp = temp_audio.name
            audio.save(audio_temp)

        audio_result = uploader.upload(
            audio_temp,
            resource_type="video",
            folder="beatvault/audio",
            use_filename=True,
            unique_filename=True,
            overwrite=False
        )

        if cover and cover.filename:

            if ext_ok(cover.filename, COVER_ALLOWED):

                cover_name = secure_filename(cover.filename)
                cover_ext = cover_name.rsplit(".", 1)[1].lower()

                with tempfile.NamedTemporaryFile(
                    delete=False,
                    suffix="." + cover_ext
                ) as temp_cover:
                    cover_temp = temp_cover.name
                    cover.save(cover_temp)

                cover_result = uploader.upload(
                    cover_temp,
                    resource_type="image",
                    folder="beatvault/covers",
                    use_filename=True,
                    unique_filename=True,
                    overwrite=False
                )

        try:
            bpm = int(request.form.get("bpm") or 0) or None
        except Exception:
            bpm = None

        supabase.table("beats").insert({
            "title": title,
            "filename": audio_result["secure_url"],
            "original_name": original_name,
            "audio_url": audio_result["secure_url"],
            "cover_url": (
                cover_result["secure_url"]
                if cover_result else None
            ),
            "audio_public_id": audio_result["public_id"],
            "cover_public_id": (
                cover_result["public_id"]
                if cover_result else None
            ),
            "bpm": bpm,
            "key_name": request.form.get(
                "key_name", ""
            ).strip(),
            "genre": request.form.get(
                "genre", ""
            ).strip()
        }).execute()

        flash("Beat published.")

    except Exception:

        app.logger.exception("Beat upload failed")

        try:
            if audio_result:
                uploader.destroy(
                    audio_result["public_id"],
                    resource_type="video"
                )
        except Exception:
            pass

        try:
            if cover_result:
                uploader.destroy(
                    cover_result["public_id"],
                    resource_type="image"
                )
        except Exception:
            pass

        flash("Upload failed. Please check your file and try again.")

    finally:

        if audio_temp:
            try:
                os.remove(audio_temp)
            except Exception:
                pass

        if cover_temp:
            try:
                os.remove(cover_temp)
            except Exception:
                pass

    return redirect(url_for("admin"))


@app.post("/delete/<int:bid>")
@admin_required
def delete(bid):

    result = (
        supabase.table("beats")
        .select("*")
        .eq("id", bid)
        .execute()
    )

    beats = result.data or []

    if not beats:
        abort(404)

    beat = beats[0]

    try:
        if beat.get("audio_public_id"):
            uploader.destroy(
                beat["audio_public_id"],
                resource_type="video"
            )
    except Exception:
        app.logger.exception("Could not delete audio")

    try:
        if beat.get("cover_public_id"):
            uploader.destroy(
                beat["cover_public_id"],
                resource_type="image"
            )
    except Exception:
        app.logger.exception("Could not delete cover")

    (
        supabase.table("beats")
        .delete()
        .eq("id", bid)
        .execute()
    )

    flash("Beat deleted.")

    return redirect(url_for("admin"))


@app.get("/audio/<path:filename>")
def audio(filename):

    if filename.startswith("http://") or filename.startswith("https://"):
        return redirect(filename)

    abort(404)


@app.get("/cover/<path:filename>")
def cover(filename):

    if filename.startswith("http://") or filename.startswith("https://"):
        return redirect(filename)

    abort(404)


@app.get("/download/<int:bid>")
def download(bid):

    result = (
        supabase.table("beats")
        .select("*")
        .eq("id", bid)
        .execute()
    )

    beats = result.data or []

    if not beats:
        abort(404)

    beat = beats[0]
    audio_url = beat.get("audio_url")

    if not audio_url:
        abort(404)

    if "/upload/" in audio_url:
        audio_url = audio_url.replace(
            "/upload/",
            "/upload/fl_attachment/",
            1
        )

    return redirect(audio_url)


@app.errorhandler(413)
def too_large(_):

    flash(f"File too large. Maximum {MAX_MB} MB.")

    return redirect(url_for("admin"))


if __name__ == "__main__":
    app.run(debug=True)

import os, sqlite3, uuid
from pathlib import Path
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, session, flash, abort, jsonify
from werkzeug.utils import secure_filename

BASE=Path(__file__).resolve().parent
UPLOADS=BASE/"uploads"; UPLOADS.mkdir(exist_ok=True)
DB=BASE/"beats.db"
ALLOWED={"mp3","wav","m4a","flac","ogg","aac"}
COVER_ALLOWED={"jpg","jpeg","png","webp"}
MAX_MB=500

app=Flask(__name__)
app.secret_key=os.environ.get("SECRET_KEY","replace-me")
app.config["MAX_CONTENT_LENGTH"]=MAX_MB*1024*1024

def conn():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def init_db():
    c=conn()
    c.execute("""CREATE TABLE IF NOT EXISTS beats(
      id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,filename TEXT NOT NULL,
      original_name TEXT NOT NULL,cover TEXT,bpm INTEGER,key_name TEXT,genre TEXT,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS settings(
      id INTEGER PRIMARY KEY CHECK(id=1),artist_name TEXT,tagline TEXT,logo_text TEXT)""")
    if not c.execute("SELECT 1 FROM settings WHERE id=1").fetchone():
        c.execute("INSERT INTO settings VALUES(1,?,?,?)",
                  ("YOUR ARTIST NAME","Instrumentals for your next record","YOUR LOGO"))
    c.commit(); c.close()

def ext_ok(name, allowed): return "." in name and name.rsplit(".",1)[1].lower() in allowed
def admin_required(f):
    @wraps(f)
    def w(*a,**kw):
        if not session.get("admin"): return redirect(url_for("login",next=request.path))
        return f(*a,**kw)
    return w

@app.context_processor
def global_settings():
    c=conn(); s=c.execute("SELECT * FROM settings WHERE id=1").fetchone(); c.close()
    return {"site":s}

@app.route("/")
def index():
    q=request.args.get("q","").strip()
    genre=request.args.get("genre","").strip()
    c=conn()
    sql="SELECT * FROM beats WHERE 1=1"; args=[]
    if q:
        sql+=" AND (title LIKE ? OR genre LIKE ? OR key_name LIKE ?)"
        args += [f"%{q}%"]*3
    if genre: sql+=" AND genre=?"; args.append(genre)
    sql+=" ORDER BY created_at DESC"
    beats=c.execute(sql,args).fetchall()
    genres=[r[0] for r in c.execute("SELECT DISTINCT genre FROM beats WHERE genre IS NOT NULL AND genre!='' ORDER BY genre").fetchall()]
    c.close()
    return render_template("index.html",beats=beats,genres=genres,q=q,genre=genre)

@app.route("/login",methods=["GET","POST"])
def login():
    if request.method=="POST":
        if request.form.get("password","")==os.environ.get("ADMIN_PASSWORD","change-me"):
            session["admin"]=True; return redirect(request.args.get("next") or url_for("admin"))
        flash("Incorrect password.")
    return render_template("login.html")

@app.post("/logout")
def logout(): session.clear(); return redirect(url_for("index"))

@app.route("/admin")
@admin_required
def admin():
    c=conn(); beats=c.execute("SELECT * FROM beats ORDER BY created_at DESC").fetchall(); c.close()
    return render_template("admin.html",beats=beats)

@app.post("/settings")
@admin_required
def settings():
    c=conn()
    c.execute("UPDATE settings SET artist_name=?,tagline=?,logo_text=? WHERE id=1",
      (request.form.get("artist_name","").strip() or "YOUR ARTIST NAME",
       request.form.get("tagline","").strip(),request.form.get("logo_text","").strip() or "YOUR LOGO"))
    c.commit(); c.close(); flash("Brand settings saved."); return redirect(url_for("admin"))

@app.post("/upload")
@admin_required
def upload():
    title=request.form.get("title","").strip(); audio=request.files.get("audio"); cover=request.files.get("cover")
    if not title or not audio or not audio.filename: flash("Title and audio file are required."); return redirect(url_for("admin"))
    if not ext_ok(audio.filename,ALLOWED): flash("Unsupported audio format."); return redirect(url_for("admin"))
    base=secure_filename(audio.filename); aext=base.rsplit(".",1)[1].lower()
    fname=f"{uuid.uuid4().hex}.{aext}"; audio.save(UPLOADS/fname)
    covername=None
    if cover and cover.filename and ext_ok(cover.filename,COVER_ALLOWED):
        covername=f"{uuid.uuid4().hex}.{cover.filename.rsplit('.',1)[1].lower()}"; cover.save(UPLOADS/covername)
    try: bpm=int(request.form.get("bpm") or 0) or None
    except: bpm=None
    c=conn(); c.execute("""INSERT INTO beats(title,filename,original_name,cover,bpm,key_name,genre)
      VALUES(?,?,?,?,?,?,?)""",(title,fname,base,covername,bpm,request.form.get("key_name","").strip(),request.form.get("genre","").strip()))
    c.commit(); c.close(); flash("Beat published."); return redirect(url_for("admin"))

@app.post("/delete/<int:bid>")
@admin_required
def delete(bid):
    c=conn(); b=c.execute("SELECT * FROM beats WHERE id=?",(bid,)).fetchone()
    if b:
        for x in (b["filename"],b["cover"]):
            if x and (UPLOADS/x).exists(): (UPLOADS/x).unlink()
        c.execute("DELETE FROM beats WHERE id=?",(bid,)); c.commit()
    c.close(); return redirect(url_for("admin"))

@app.get("/audio/<path:filename>")
def audio(filename): return send_from_directory(UPLOADS,filename)
@app.get("/cover/<path:filename>")
def cover(filename): return send_from_directory(UPLOADS,filename)
@app.get("/download/<int:bid>")
def download(bid):
    c=conn(); b=c.execute("SELECT * FROM beats WHERE id=?",(bid,)).fetchone(); c.close()
    if not b: abort(404)
    return send_from_directory(UPLOADS,b["filename"],as_attachment=True,download_name=b["original_name"])

@app.errorhandler(413)
def too_large(_): flash(f"File too large. Maximum {MAX_MB} MB."); return redirect(url_for("admin"))

init_db()
if __name__=="__main__": app.run(debug=True)

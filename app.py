import os
import sqlite3
import click
import secrets
import hmac
from urllib.parse import urlsplit
from flask import Flask, render_template, request, redirect, session, jsonify, g, abort
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or os.urandom(32)  

app.config.update(
    MAX_CONTENT_LENGTH=64 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

@app.context_processor
def csrf_context():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return {"csrf_token": session["csrf_token"]}

@app.before_request
def verify_csrf():
    if request.method == "POST":
        expected = session.get("csrf_token", "")
        supplied = request.form.get("csrf_token", "")
        if not expected or not hmac.compare_digest(expected, supplied):
            abort(400, description="فرم منقضی شده است. صفحه را تازه کنید و دوباره تلاش کنید.")

@app.errorhandler(400)
@app.errorhandler(403)
@app.errorhandler(404)
@app.errorhandler(413)
def show_error(error):
    return render_template("error.html", message=error.description, code=error.code), error.code

BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, "songapp.db")

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

@app.cli.command("init-db")
def init_db():
    """Create missing tables without deleting existing records."""
    with open(os.path.join(BASE_DIR, "schema.sql"), encoding="utf-8") as schema:
        get_db().executescript(schema.read())
    click.echo("Database initialized.")

# Register
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        if not username or not password:
            abort(400, description="نام کاربری و رمز لازم است")

        if not 3 <= len(username) <= 80 or not 8 <= len(password) <= 256:
            abort(400, description="نام کاربری باید ۳ تا ۸۰ حرف و رمز عبور ۸ تا ۲۵۶ حرف باشد.")
        hash_pw = generate_password_hash(password)
        db = get_db()
        try:
            db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", (username, hash_pw))
            db.commit()
        except sqlite3.IntegrityError:
            abort(400, description="نام کاربری قبلاً گرفته شده")
        return redirect("/login")
    return render_template("register.html")

# Login
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        db = get_db()
        row = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if not row or not check_password_hash(row["hash"], password):
            abort(400, description="نام کاربری یا رمز اشتباه است")
        session.clear()
        session["user_id"] = row["id"]
        session["username"] = row["username"]
        return redirect("/")
    return render_template("login.html")

# Logout
@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect("/login")

# Index
@app.route("/")
def index():
    db = get_db()
    songs = db.execute(
        "SELECT s.id, s.title, s.file_path, s.added_at, u.username FROM songs s JOIN users u ON s.added_by = u.id ORDER BY s.added_at DESC"
    ).fetchall()

    songs_with_comments = []
    for s in songs:
        comments = db.execute(
            "SELECT c.comment, c.posted_at, u.username FROM comments c JOIN users u ON c.user_id = u.id WHERE c.song_id = ? ORDER BY c.posted_at DESC",
            (s["id"],)
        ).fetchall()
        songs_with_comments.append({"id": s["id"], "title": s["title"], "file_path": s["file_path"], "added_by": s["username"], "added_at": s["added_at"], "comments": comments})

    return render_template("index.html", songs=songs_with_comments)

# Add song
@app.route("/add_song", methods=["POST"])
def add_song():
    if "user_id" not in session:
        abort(403, description="ابتدا وارد شوید")

    title = request.form.get("title", "").strip()
    file_path = request.form.get("file_path", "").strip()

    if not title or not file_path:
        abort(400, description="عنوان و لینک لازم است")

    try:
        audio_url = urlsplit(file_path)
        valid_url = audio_url.scheme in ("http", "https") and bool(audio_url.hostname)
    except ValueError:
        valid_url = False
    if not valid_url or len(file_path) > 2048 or len(title) > 200:
        abort(400, description="عنوان حداکثر ۲۰۰ حرف و لینک معتبر HTTP(S) لازم است.")

    db = get_db()
    db.execute(
        "INSERT INTO songs (title, file_path, added_by) VALUES (?, ?, ?)",
        (title, file_path, session["user_id"]),
    )
    db.commit()
    return redirect("/")

# Add comment
@app.route("/add_comment", methods=["POST"])
def add_comment():
    if "user_id" not in session:
        abort(403, description="ابتدا وارد شوید")
    song_id = request.form.get("song_id")
    comment = request.form.get("comment", "").strip()
    if not song_id or not comment or len(comment) > 5000:
        abort(400, description="اطلاعات ناقص است")
    db = get_db()
    if not db.execute("SELECT id FROM songs WHERE id = ?", (song_id,)).fetchone():
        abort(404, description="آهنگ پیدا نشد")
    db.execute("INSERT INTO comments (song_id, user_id, comment) VALUES (?, ?, ?)", (song_id, session["user_id"], comment))
    db.commit()
    return redirect("/")

# API
@app.route("/api/songs")
def api_songs():
    db = get_db()
    songs = db.execute("SELECT id, title FROM songs ORDER BY added_at DESC").fetchall()
    out = []
    for s in songs:
        comments = db.execute(
            "SELECT c.comment, c.posted_at, u.username FROM comments c JOIN users u ON c.user_id = u.id WHERE c.song_id = ? ORDER BY c.posted_at DESC",
            (s["id"],)
        ).fetchall()
        out.append({
            "id": s["id"],
            "title": s["title"],
            "comments": [{"user": c["username"], "comment": c["comment"], "when": c["posted_at"]} for c in comments]
        })
    return jsonify(out)

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")

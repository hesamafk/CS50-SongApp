import os
import sqlite3
from flask import Flask, render_template, request, redirect, session, jsonify, g
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or os.urandom(32)  

BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, "songapp.db")

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

# Register
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password")
        if not username or not password:
            return "نام کاربری و رمز لازم است", 400

        hash_pw = generate_password_hash(password)
        db = get_db()
        try:
            db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", (username, hash_pw))
            db.commit()
        except sqlite3.IntegrityError:
            return "نام کاربری قبلاً گرفته شده", 400
        return redirect("/login")
    return render_template("register.html")

# Login
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password")
        db = get_db()
        row = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if not row or not check_password_hash(row["hash"], password):
            return "نام کاربری یا رمز اشتباه است", 400
        session["user_id"] = row["id"]
        session["username"] = row["username"]
        return redirect("/")
    return render_template("login.html")

# Logout
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# Index
@app.route("/")
def index():
    db = get_db()
    songs = db.execute(
        "SELECT s.id, s.title, s.added_at, u.username FROM songs s JOIN users u ON s.added_by = u.id ORDER BY s.added_at DESC"
    ).fetchall()

    songs_with_comments = []
    for s in songs:
        comments = db.execute(
            "SELECT c.comment, c.posted_at, u.username FROM comments c JOIN users u ON c.user_id = u.id WHERE c.song_id = ? ORDER BY c.posted_at DESC",
            (s["id"],)
        ).fetchall()
        songs_with_comments.append({"id": s["id"], "title": s["title"], "added_by": s["username"], "added_at": s["added_at"], "comments": comments})

    return render_template("index.html", songs=songs_with_comments)

# Add song
@app.route("/add_song", methods=["POST"])
def add_song():
    if "user_id" not in session:
        return "ابتدا وارد شوید", 403

    title = request.form.get("title", "").strip()
    file_path = request.form.get("file_path", "").strip()

    if not title or not file_path:
        return "عنوان و لینک لازم است", 400

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
        return "ابتدا وارد شوید", 403
    song_id = request.form.get("song_id")
    comment = request.form.get("comment", "").strip()
    if not song_id or not comment:
        return "اطلاعات ناقص است", 400
    db = get_db()
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
    app.run(debug=True)

from flask import (
    Flask, render_template, request,
    jsonify, redirect, url_for,
    flash, abort
)

from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    logout_user,
    login_required,
    current_user
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from anime_model import AnimeRecommender
from datetime import datetime
from functools import wraps

import requests
import re
import os


# ================= APP =================
app = Flask(__name__)
app.secret_key = "animefinder-secret-key"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///anime.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
model = AnimeRecommender("anime.csv")


# ================= MODELS =================

class User(UserMixin, db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    username   = db.Column(db.String(80), unique=True, nullable=False)
    email      = db.Column(db.String(120), unique=True, nullable=False)
    password   = db.Column(db.String(200), nullable=False)
    role       = db.Column(db.String(20), default="user")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    favorites  = db.relationship("Favorite", backref="user", cascade="all, delete-orphan")
    history    = db.relationship("WatchHistory", backref="user", cascade="all, delete-orphan")


class Favorite(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    anime_id    = db.Column(db.Integer, nullable=False)
    anime_name  = db.Column(db.String(200))
    anime_image = db.Column(db.String(500))
    anime_score = db.Column(db.String(20))
    added_at    = db.Column(db.DateTime, default=datetime.utcnow)


class WatchHistory(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    anime_id    = db.Column(db.Integer, nullable=False)
    anime_name  = db.Column(db.String(200))
    anime_image = db.Column(db.String(500))
    episode     = db.Column(db.Integer, nullable=False)
    watched_at  = db.Column(db.DateTime, default=datetime.utcnow)


# ================= LOGIN =================

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ================= ADMIN =================

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("login"))
        if current_user.role != "admin":
            abort(403)
        return f(*args, **kwargs)
    return wrapper


# ================= CREATE ADMIN =================

def create_admin():
    if User.query.filter_by(username="admin").first():
        return
    admin = User(
        username="admin",
        email="admin@gmail.com",
        password=generate_password_hash("Admin123"),
        role="admin"
    )
    db.session.add(admin)
    db.session.commit()


# ================= ANILIST =================

def mal_to_anilist(mal_id):
    query = """
    query ($malId:Int){
      Media(idMal:$malId, type:ANIME){ id }
    }
    """
    try:
        response = requests.post(
            "https://graphql.anilist.co",
            json={"query": query, "variables": {"malId": mal_id}},
            timeout=5
        )
        return response.json()["data"]["Media"]["id"]
    except Exception:
        return mal_id


# ================= HOME =================

@app.route("/")
@login_required
def home():
    return render_template(
        "index.html",
        genres=model.get_all_genres(),
        types=model.get_all_types(),
        trending=model.get_top_anime()
    )


# ================= REGISTER =================

@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email    = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm  = request.form.get("confirm", "")

        if not re.match(r"^[a-zA-Z0-9_]{3,20}$", username):
            flash("Invalid username", "error")
            return render_template("register.html")

        if not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
            flash("Invalid email", "error")
            return render_template("register.html")

        if not re.match(r"^(?=.*[A-Z])(?=.*[a-z])(?=.*\d).{8,}$", password):
            flash("Weak password", "error")
            return render_template("register.html")

        if password != confirm:
            flash("Passwords do not match", "error")
            return render_template("register.html")

        if User.query.filter_by(username=username).first():
            flash("Username exists", "error")
            return render_template("register.html")

        if User.query.filter_by(email=email).first():
            flash("Email exists", "error")
            return render_template("register.html")

        user = User(
            username=username,
            email=email,
            password=generate_password_hash(password)
        )
        db.session.add(user)
        db.session.commit()
        login_user(user)
        return redirect(url_for("home"))

    return render_template("register.html")


# ================= LOGIN =================

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for("home"))

        flash("Wrong credentials", "error")

    return render_template("login.html")


# ================= LOGOUT =================

@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# ================= RECOMMEND =================

@app.route("/recommend", methods=["POST"])
@login_required
def recommend():
    search     = request.form.get("search", "").strip()
    genre      = request.form.get("genre", "All")
    anime_type = request.form.get("type", "All")
    min_score  = request.form.get("score", 0)

    results = model.recommend(
        search=search or None,
        genre=genre,
        anime_type=anime_type,
        min_score=min_score
    )
    return render_template("results.html", results=results)


# ================= ANIME DETAIL =================

@app.route("/anime/<int:anime_id>")
@login_required
def anime_detail(anime_id):
    anime = model.get_anime_by_id(anime_id)
    if not anime:
        abort(404)

    similar = model.recommend(
        genre=str(anime.get("genres", "")).split(",")[0].strip(),
        anime_type=anime.get("type", "All")
    )
    similar = [a for a in similar if a["anime_id"] != anime_id][:12]

    is_favorite = Favorite.query.filter_by(
        user_id=current_user.id,
        anime_id=anime_id
    ).first() is not None

    return render_template("details.html", anime=anime, similar=similar, is_favorite=is_favorite)


# ================= EPISODES =================

@app.route("/episodes/<int:anime_id>")
@login_required
def episodes(anime_id):
    anime = model.get_anime_by_id(anime_id)
    if not anime:
        abort(404)

    total_episodes = anime.get("episodes", 0)
    try:
        total_episodes = int(total_episodes)
    except (ValueError, TypeError):
        total_episodes = 0

    episodes_list = []
    try:
        resp = requests.get(f"https://api.jikan.moe/v4/anime/{anime_id}/episodes", timeout=5)
        episodes_list = resp.json().get("data", [])
    except Exception:
        pass

    return render_template("episodes.html", anime=anime, anime_id=anime_id,
                           episodes=episodes_list, total_episodes=total_episodes)


# ================= WATCH =================

@app.route("/watch/<int:anime_id>/<int:episode>")
@login_required
def watch(anime_id, episode):
    anime = model.get_anime_by_id(anime_id)
    if not anime:
        abort(404)

    episode_info = {"title": None, "filler": False}
    try:
        resp = requests.get(f"https://api.jikan.moe/v4/anime/{anime_id}/episodes/{episode}", timeout=5)
        ep_data = resp.json().get("data", {})
        episode_info = {"title": ep_data.get("title"), "filler": ep_data.get("filler", False)}
    except Exception:
        pass

    existing = WatchHistory.query.filter_by(
        user_id=current_user.id, anime_id=anime_id, episode=episode
    ).first()

    if not existing:
        db.session.add(WatchHistory(
            user_id=current_user.id,
            anime_id=anime_id,
            anime_name=anime.get("name", ""),
            anime_image=anime.get("image_url", ""),
            episode=episode
        ))
        db.session.commit()

    return render_template("watch.html", anime=anime, anime_id=anime_id,
                           episode=episode, episode_info=episode_info)


# ================= ADMIN =================

@app.route("/admin/users")
@login_required
@admin_required
def admin_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template("users.html", users=users)


@app.route("/admin/delete_user/<int:user_id>", methods=["POST"])
@login_required
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("Cannot delete yourself", "error")
        return redirect(url_for("admin_users"))
    db.session.delete(user)
    db.session.commit()
    flash("User deleted", "success")
    return redirect(url_for("admin_users"))


# ================= PROFILE =================

@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html')


@app.route('/edit_username', methods=['POST'])
@login_required
def edit_username():
    new_username = request.form.get('username', '').strip()

    if not re.match(r'^[a-zA-Z0-9_]{3,20}$', new_username):
        flash('Invalid username (3-20 chars, letters/digits/_)', 'error')
        return redirect(url_for('profile'))

    if User.query.filter_by(username=new_username).first():
        flash('Username already taken', 'error')
        return redirect(url_for('profile'))

    current_user.username = new_username
    db.session.commit()
    flash('Username updated successfully', 'success')
    return redirect(url_for('profile'))


@app.route('/edit_email', methods=['POST'])
@login_required
def edit_email():
    new_email = request.form.get('email', '').strip()

    if not re.match(r'^[^@]+@[^@]+\.[^@]+$', new_email):
        flash('Invalid email address', 'error')
        return redirect(url_for('profile'))

    if User.query.filter_by(email=new_email).first():
        flash('Email already in use', 'error')
        return redirect(url_for('profile'))

    current_user.email = new_email
    db.session.commit()
    flash('Email updated successfully', 'success')
    return redirect(url_for('profile'))


@app.route('/change_password', methods=['POST'])
@login_required
def change_password():
    current_password = request.form.get('current_password', '')
    new_password     = request.form.get('new_password', '')
    confirm_password = request.form.get('confirm_password', '')

    if not check_password_hash(current_user.password, current_password):
        flash('Current password is incorrect', 'error')
        return redirect(url_for('profile'))

    if not re.match(r'^(?=.*[A-Z])(?=.*[a-z])(?=.*\d).{8,}$', new_password):
        flash('Weak password: min 8 chars, uppercase, lowercase, digit', 'error')
        return redirect(url_for('profile'))

    if new_password != confirm_password:
        flash('Passwords do not match', 'error')
        return redirect(url_for('profile'))

    current_user.password = generate_password_hash(new_password)
    db.session.commit()
    flash('Password changed successfully', 'success')
    return redirect(url_for('profile'))


@app.route('/change_avatar', methods=['POST'])
@login_required
def change_avatar():
    return redirect(url_for('profile'))


# ================= FAVORITES =================

@app.route("/add_favorite/<int:anime_id>", methods=["POST"])
@login_required
def add_favorite(anime_id):
    anime = model.get_anime_by_id(anime_id)
    if not anime:
        return jsonify({"status": "error"})

    if Favorite.query.filter_by(user_id=current_user.id, anime_id=anime_id).first():
        return jsonify({"status": "exists"})

    db.session.add(Favorite(
        user_id=current_user.id,
        anime_id=anime_id,
        anime_name=anime.get("name", ""),
        anime_image=anime.get("image_url", ""),
        anime_score=str(anime.get("score", ""))
    ))
    db.session.commit()
    return jsonify({"status": "ok"})


@app.route("/remove_favorite/<int:anime_id>", methods=["POST"])
@login_required
def remove_favorite(anime_id):
    fav = Favorite.query.filter_by(user_id=current_user.id, anime_id=anime_id).first()
    if fav:
        db.session.delete(fav)
        db.session.commit()
    return jsonify({"status": "ok"})


@app.route("/favorites")
@login_required
def favorites_page():
    favs = Favorite.query.filter_by(user_id=current_user.id).all()
    return render_template("favorites.html", favorites=favs)


# ================= HISTORY =================

@app.route("/history")
@login_required
def history_page():
    history = WatchHistory.query.filter_by(user_id=current_user.id)\
                                .order_by(WatchHistory.watched_at.desc()).all()
    return render_template("history.html", history=history)


@app.route("/clear_history", methods=["POST"])
@login_required
def clear_history():
    WatchHistory.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    return jsonify({"status": "ok"})


# ================= INIT =================

with app.app_context():
    db.create_all()
    create_admin()


# ================= RUN =================

if __name__ == "__main__":
    app.run(debug=True)
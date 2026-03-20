from __future__ import annotations

from datetime import datetime

from flask import Flask, abort, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from medha import init_db
from medha.extensions import db
from medha.models import ChatMessage, MindMapNode, Task, User

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = "change-me-in-production"

db.init_app(app)
init_db(app)


def current_user_id() -> int | None:
    uid = session.get("user_id")
    return int(uid) if uid else None


def require_login() -> int:
    uid = current_user_id()
    if not uid:
        abort(401)
    return uid


def get_chat_mode() -> str:
    mode = session.get("chat_mode", "sherlock")
    return mode if mode in ("sherlock", "assistant") else "sherlock"


def infer_user_state(user_id: int, recent_text: str) -> tuple[dict, dict]:
    text_l = (recent_text or "").lower()
    evidence: dict = {"text_flags": [], "behavior": {}}

    open_count = Task.query.filter_by(user_id=user_id, completed=False).count()
    done_total = Task.query.filter_by(user_id=user_id, completed=True).count()
    evidence["behavior"] = {"open_tasks": open_count, "completed_total": done_total}

    stress_score = 0
    focus_score = 0
    load_score = 0
    mood_score = 0
    conf_score = 0

    for kw in ["overwhelmed", "anxious", "panic", "stressed", "burnt out", "burned out", "tired"]:
        if kw in text_l:
            stress_score += 2
            evidence["text_flags"].append(kw)
    for kw in ["can't focus", "cant focus", "distracted", "adhd", "scrolling", "procrastinating"]:
        if kw in text_l:
            focus_score -= 2
            evidence["text_flags"].append(kw)
    for kw in ["too much", "many things", "no time", "deadline", "urgent"]:
        if kw in text_l:
            load_score += 1
            evidence["text_flags"].append(kw)
    for kw in ["sad", "hopeless", "angry", "irritated", "frustrated"]:
        if kw in text_l:
            mood_score -= 1
            evidence["text_flags"].append(kw)
    for kw in ["fine", "okay", "good", "great", "excited"]:
        if kw in text_l:
            mood_score += 1
    for kw in ["i can", "i will", "done", "progress"]:
        if kw in text_l:
            conf_score += 1

    if open_count >= 12:
        load_score += 2

    def bucket(v: int) -> str:
        if v <= -1:
            return "low"
        if v >= 2:
            return "high"
        return "mid"

    def mood_bucket(v: int) -> str:
        if v <= -1:
            return "neg"
        if v >= 1:
            return "pos"
        return "neutral"

    state = {
        "stress": bucket(stress_score),
        "focus": bucket(focus_score),
        "mood": mood_bucket(mood_score),
        "load": bucket(load_score),
        "confidence": bucket(conf_score),
    }
    return state, evidence


def generate_chat_reply(mode: str, user_text: str, state: dict) -> str:
    text = (user_text or "").strip()
    focus = state.get("focus")
    stress = state.get("stress")
    load = state.get("load")

    if mode == "assistant":
        parts = []
        if stress == "high":
            parts.append("Let’s lower the noise. One step at a time.")
        if load == "high":
            parts.append("You’ve got a lot on your plate. We’ll pick a smallest-next-action.")
        parts.append("Tell me the one outcome you want in the next 30 minutes.")
        parts.append("Choose one: (A) quick win 10 min, (B) deep work 25 min, (C) cleanup 5 min.")
        return "\n\n".join(parts)

    opener = "Alright, my friend—give me the clues."
    if focus == "low":
        opener = "Interesting. Your attention is slipping—classic case."
    if stress == "high":
        opener = "Noted: elevated pressure. We’ll handle it like a clean investigation."

    questions = [
        "Quick check: is this more *overwhelm* or *boredom*?",
        "What’s the ONE thing you’re avoiding (be honest)?",
        "If we made progress in 10 minutes, what would that look like?",
    ]
    if load == "high":
        questions.insert(0, "You’ve got many threads open. Which one is most urgent vs most important?")

    return (
        f"{opener}\n\n"
        f"You said: “{text}”\n\n"
        "Let’s narrow it down.\n\n"
        + "\n".join(f"- {q}" for q in questions)
    )


# ---------- Auth ---------- #

@app.get("/", endpoint="auth.login")
def login():
    if current_user_id():
        return redirect(url_for("dashboard.dashboard"))
    error = session.pop("auth_error", None)
    return render_template("login.html", error=error)


@app.post("/login", endpoint="auth.login_post")
def login_post():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    user = User.query.filter_by(username=username).first()
    ok = False
    if user:
        if user.password_hash:
            ok = check_password_hash(user.password_hash, password)
        elif user.password:
            ok = user.password == password
            if ok:
                user.password_hash = generate_password_hash(password)
                db.session.commit()

    if not user or not ok:
        session["auth_error"] = "Invalid username or password."
        return redirect(url_for("auth.login"))

    session["user_id"] = user.id
    session["username"] = user.username
    return redirect(url_for("dashboard.dashboard"))


@app.route("/signup", methods=["GET", "POST"], endpoint="auth.signup")
def signup():
    if request.method == "GET":
        if current_user_id():
            return redirect(url_for("dashboard.dashboard"))
        error = session.pop("auth_error", None)
        return render_template("signup.html", error=error)

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    if not username or not password:
        session["auth_error"] = "Please enter a username and password."
        return redirect(url_for("auth.signup"))

    existing = User.query.filter_by(username=username).first()
    if existing:
        session["auth_error"] = "Username already exists. Please choose another."
        return redirect(url_for("auth.signup"))

    u = User(username=username, password_hash=generate_password_hash(password))
    db.session.add(u)
    db.session.commit()
    session["user_id"] = u.id
    session["username"] = u.username
    return redirect(url_for("dashboard.dashboard"))


@app.get("/logout", endpoint="auth.logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


# ---------- Pages ---------- #

@app.get("/dashboard", endpoint="dashboard.dashboard")
def dashboard():
    uid = require_login()
    user = db.session.get(User, uid)
    if not user:
        session.clear()
        return redirect(url_for("auth.login"))

    total_tasks = Task.query.filter_by(user_id=uid).count()
    open_tasks = Task.query.filter_by(user_id=uid, completed=False).count()
    completed_recent = (
        Task.query.filter_by(user_id=uid, completed=True)
        .order_by(Task.completed_at.desc(), Task.created_at.desc())
        .limit(6)
        .all()
    )

    return render_template(
        "dashboard.html",
        active_page="dashboard",
        page_title="MEDHA · Dashboard",
        page_heading=f"Welcome, {user.username}",
        page_subtitle="Overview only.",
        name=user.username,
        total_tasks=total_tasks,
        open_tasks=open_tasks,
        completed_recent=completed_recent,
    )


@app.get("/tasks", endpoint="tasks.tasks")
def tasks():
    uid = require_login()
    user = db.session.get(User, uid)
    if not user:
        session.clear()
        return redirect(url_for("auth.login"))
    flt = request.args.get("filter", "open")
    flt = flt if flt in ("open", "completed", "all") else "open"
    q = (request.args.get("q") or "").strip()

    base = Task.query.filter_by(user_id=uid)
    if flt == "open":
        base = base.filter_by(completed=False)
    elif flt == "completed":
        base = base.filter_by(completed=True)

    if q:
        base = base.filter(Task.title.ilike(f"%{q}%"))

    # Keep both lists for counts/sections
    open_tasks = (
        Task.query.filter_by(user_id=uid, completed=False)
        .order_by(Task.created_at.desc())
        .all()
    )
    completed_tasks = (
        Task.query.filter_by(user_id=uid, completed=True)
        .order_by(Task.completed_at.desc(), Task.created_at.desc())
        .all()
    )

    filtered_tasks = (
        base.order_by(Task.completed.asc(), Task.priority.desc(), Task.created_at.desc())
        .limit(200)
        .all()
    )
    return render_template(
        "tasks.html",
        active_page="tasks",
        page_title="MEDHA · Tasks",
        page_heading="Tasks",
        page_subtitle="Add, delete, complete.",
        name=user.username,
        open_tasks=open_tasks,
        completed_tasks=completed_tasks,
        filtered_tasks=filtered_tasks,
        filter=flt,
        q=q,
    )


@app.post("/add_task", endpoint="tasks.add_task")
def add_task():
    uid = require_login()
    title = request.form.get("title", "").strip()
    pr = request.form.get("priority", "0")
    if title:
        try:
            pr_i = int(pr)
        except Exception:
            pr_i = 0
        pr_i = 2 if pr_i == 2 else (1 if pr_i == 1 else 0)
        db.session.add(Task(title=title, user_id=uid, priority=pr_i))
        db.session.commit()
    return redirect(url_for("tasks.tasks"))


@app.post("/set_priority/<int:task_id>", endpoint="tasks.set_priority")
def set_priority(task_id: int):
    uid = require_login()
    t = db.session.get(Task, task_id)
    if not t or t.user_id != uid:
        abort(404)
    try:
        pr_i = int(request.form.get("priority", "0"))
    except Exception:
        pr_i = 0
    pr_i = 2 if pr_i == 2 else (1 if pr_i == 1 else 0)
    t.priority = pr_i
    db.session.commit()
    return redirect(url_for("tasks", filter=request.args.get("filter", "open"), q=request.args.get("q", "")))


@app.post("/toggle_task/<int:task_id>", endpoint="tasks.toggle_task")
def toggle_task(task_id: int):
    uid = require_login()
    t = db.session.get(Task, task_id)
    if not t or t.user_id != uid:
        abort(404)
    t.completed = not t.completed
    t.completed_at = datetime.utcnow() if t.completed else None
    db.session.commit()
    return redirect(url_for("tasks.tasks"))


@app.post("/delete_task/<int:task_id>", endpoint="tasks.delete_task")
def delete_task(task_id: int):
    uid = require_login()
    t = db.session.get(Task, task_id)
    if not t or t.user_id != uid:
        abort(404)
    db.session.delete(t)
    db.session.commit()
    return redirect(url_for("tasks.tasks"))


@app.get("/chat", endpoint="chat.chat")
def chat():
    uid = require_login()
    user = db.session.get(User, uid)
    if not user:
        session.clear()
        return redirect(url_for("auth.login"))
    mode = get_chat_mode()
    msgs = ChatMessage.query.filter_by(user_id=uid).order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc()).all()
    return render_template(
        "chat.html",
        active_page="chat",
        page_title="MEDHA · Chat",
        page_heading="Sherlock Chat",
        page_subtitle="Sherlock Mode or Assistant Mode.",
        name=user.username,
        mode=mode,
        messages=msgs,
    )


@app.post("/chat/mode", endpoint="chat.chat_mode")
def chat_mode():
    require_login()
    mode = request.form.get("mode", "sherlock")
    if mode in ("sherlock", "assistant"):
        session["chat_mode"] = mode
    return redirect(url_for("chat.chat"))


@app.post("/chat/send", endpoint="chat.chat_send")
def chat_send():
    uid = require_login()
    mode = get_chat_mode()
    text_in = request.form.get("message", "").strip()
    if not text_in:
        return redirect(url_for("chat.chat"))

    state, evidence = infer_user_state(uid, text_in)
    reply = generate_chat_reply(mode, text_in, state)

    db.session.add(ChatMessage(user_id=uid, role="user", content=text_in, mode=mode))
    db.session.add(ChatMessage(user_id=uid, role="assistant", content=reply, mode=mode))
    db.session.commit()
    return redirect(url_for("chat.chat"))


@app.get("/focus")
def focus():
    uid = require_login()
    user = db.session.get(User, uid)
    if not user:
        session.clear()
        return redirect(url_for("auth.login"))
    return render_template(
        "focus.html",
        active_page="focus",
        page_title="MEDHA · Focus",
        page_heading="Focus",
        page_subtitle="A calm focus space (placeholder).",
        name=user.username,
    )


@app.get("/settings", endpoint="settings.settings")
def settings():
    uid = require_login()
    user = db.session.get(User, uid)
    if not user:
        session.clear()
        return redirect(url_for("auth.login"))
    return render_template(
        "settings.html",
        active_page="settings",
        page_title="MEDHA · Settings",
        page_heading="Settings",
        page_subtitle="Basic settings.",
        name=user.username,
    )


@app.get("/settings/export", endpoint="settings.settings_export")
def settings_export():
    uid = require_login()
    user = db.session.get(User, uid)
    tasks = Task.query.filter_by(user_id=uid).order_by(Task.created_at.asc()).all()
    chats = ChatMessage.query.filter_by(user_id=uid).order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc()).all()

    payload = {
        "user": {"username": user.username if user else "User"},
        "tasks": [
            {
                "id": t.id,
                "title": t.title,
                "completed": bool(t.completed),
                "created_at": (t.created_at.isoformat() if t.created_at else None),
                "completed_at": (t.completed_at.isoformat() if t.completed_at else None),
            }
            for t in tasks
        ],
        "chat": [
            {
                "id": m.id,
                "role": m.role,
                "mode": m.mode,
                "content": m.content,
                "created_at": (m.created_at.isoformat() if m.created_at else None),
            }
            for m in chats
        ],
    }

    from flask import Response
    import json

    return Response(
        json.dumps(payload, ensure_ascii=False, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=medha_export.json"},
    )


@app.post("/settings/clear_chat", endpoint="settings.settings_clear_chat")
def settings_clear_chat():
    uid = require_login()
    ChatMessage.query.filter_by(user_id=uid).delete()
    db.session.commit()
    return redirect(url_for("settings.settings"))


@app.post("/settings/clear_completed", endpoint="settings.settings_clear_completed")
def settings_clear_completed():
    uid = require_login()
    Task.query.filter_by(user_id=uid, completed=True).delete()
    db.session.commit()
    return redirect(url_for("settings.settings"))


@app.errorhandler(401)
def unauthorized(_err):
    return redirect(url_for("auth.login"))

@app.get("/mindmap", endpoint="mindmap.mindmap")
def mindmap():
    uid = require_login()
    user = db.session.get(User, uid)
    nodes = MindMapNode.query.filter_by(user_id=uid).order_by(MindMapNode.created_at.desc()).all()
    # For basic visual positioning, provide nodes to the template
    return render_template(
        "mindmap.html",
        active_page="mindmap",
        page_title="MEDHA · Mind Map",
        page_heading="Mind Map",
        page_subtitle="Organize your thoughts.",
        name=user.username,
        nodes=nodes,
    )

@app.post("/mindmap_add", endpoint="mindmap.mindmap_add")
def mindmap_add():
    uid = require_login()
    content = request.form.get("content", "").strip()
    if content:
        # Default positioning roughly near the center (we'll rely on frontend or just zero)
        db.session.add(MindMapNode(user_id=uid, content=content, x=0, y=0))
        db.session.commit()
    return redirect(url_for("mindmap.mindmap"))

@app.post("/mindmap_delete/<int:node_id>", endpoint="mindmap.mindmap_delete")
def mindmap_delete(node_id: int):
    uid = require_login()
    node = db.session.get(MindMapNode, node_id)
    if not node or node.user_id != uid:
        abort(404)
    db.session.delete(node)
    db.session.commit()
    return redirect(url_for("mindmap.mindmap"))

@app.post("/mindmap_api/save_pos", endpoint="mindmap.mindmap_save_pos")
def mindmap_save_pos():
    uid = require_login()
    data = request.json or {}
    for item in data.get("nodes", []):
        node = db.session.get(MindMapNode, item["id"])
        if node and node.user_id == uid:
            node.x = item.get("x", 0)
            node.y = item.get("y", 0)
    db.session.commit()
    return {"status": "ok"}

@app.post("/chat_api", endpoint="chat.chat_api")
def chat_api():
    uid = require_login()
    mode = get_chat_mode()
    data = request.json or {}
    text_in = data.get("message", "").strip()
    if not text_in:
        return {"error": "Empty message"}, 400

    state, evidence = infer_user_state(uid, text_in)
    reply = generate_chat_reply(mode, text_in, state)

    db.session.add(ChatMessage(user_id=uid, role="user", content=text_in, mode=mode))
    db.session.add(ChatMessage(user_id=uid, role="assistant", content=reply, mode=mode))
    db.session.commit()

    return {
        "reply": reply,
        "mode": mode
    }

if __name__ == "__main__":
    app.run(debug=True)
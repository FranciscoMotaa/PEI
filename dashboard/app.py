"""
dashboard/app.py — Dashboard web para o sistema IoT
=====================================================
Lê a base de dados SQLite partilhada com o ai-server
e apresenta as classificações em tempo real.
"""

import os
import sqlite3
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, jsonify

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "supersecretkey123")

DB_PATH       = "/app/data/iot_traffic.db"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "iot2025")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


# ── Login ─────────────────────────────────────────────────
@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("index"))
        error = "Password incorreta."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── Dashboard principal ────────────────────────────────────
@app.route("/")
@login_required
def index():
    conn = get_db()

    # Últimas 50 classificações
    rows = conn.execute("""
        SELECT * FROM classifications
        ORDER BY timestamp DESC LIMIT 50
    """).fetchall()

    # Contagem por classe
    stats = conn.execute("""
        SELECT predicted, COUNT(*) as count
        FROM classifications
        GROUP BY predicted
        ORDER BY count DESC
    """).fetchall()

    # Contagem por dispositivo
    devices = conn.execute("""
        SELECT device_id, COUNT(*) as count,
               AVG(confidence) as avg_conf
        FROM classifications
        GROUP BY device_id
    """).fetchall()

    conn.close()
    return render_template("index.html", rows=rows, stats=stats, devices=devices)


# ── API JSON para auto-refresh ─────────────────────────────
@app.route("/api/latest")
@login_required
def api_latest():
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM classifications
        ORDER BY timestamp DESC LIMIT 20
    """).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/stats")
@login_required
def api_stats():
    conn = get_db()
    stats = conn.execute("""
        SELECT predicted, COUNT(*) as count
        FROM classifications
        GROUP BY predicted
        ORDER BY count DESC
    """).fetchall()
    conn.close()
    return jsonify([dict(r) for r in stats])


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)

"""
dashboard/app.py - interface web para visualizar as classificações do ai-server

Lê a base de dados SQLite partilhada e apresenta os resultados em tempo real.
"""

import csv
import io
import os
import sqlite3
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
import docker

try:
    docker_client = docker.from_env()
except Exception as e:
    print("Aviso: Falha ao ligar ao Docker socket:", e)
    docker_client = None

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


# ── API JSON para o Terminal "Matrix" ─────────────────────────────
@app.route("/api/terminal_feed")
@login_required
def api_terminal_feed():
    try:
        conn = get_db()
        # Se a tabela raw_packets ainda não existir (arranque inicial), ignora
        raw_rows = []
        try:
            raw_rows = conn.execute("SELECT timestamp, src_ip, dst_ip, size, payload_hex, src_port, dst_port, ttl FROM raw_packets ORDER BY id DESC LIMIT 40").fetchall()
        except sqlite3.OperationalError:
            # Fallback se a alter table falhou
            raw_rows = conn.execute("SELECT timestamp, src_ip, dst_ip, size FROM raw_packets ORDER BY id DESC LIMIT 40").fetchall()
            
        cls_rows = conn.execute("SELECT timestamp, device_id, predicted, confidence, avg_size, avg_iat, num_packets FROM classifications ORDER BY id DESC LIMIT 20").fetchall()
        conn.close()
        
        feed = []
        for r in raw_rows:
            rd = dict(r)
            feed.append({
                "type": "packet",
                "timestamp": rd["timestamp"],
                "src_ip": rd["src_ip"],
                "dst_ip": rd["dst_ip"],
                "size": rd["size"],
                "payload_hex": rd.get("payload_hex", "17 03 03 ..."),
                "src_port": rd.get("src_port", "---"),
                "dst_port": rd.get("dst_port", "---"),
                "ttl": rd.get("ttl", "---")
            })
            
        for c in cls_rows:
            feed.append({
                "type": "classification",
                "timestamp": c["timestamp"],
                "device_id": c["device_id"],
                "predicted": c["predicted"],
                "confidence": c["confidence"],
                "avg_size": c["avg_size"],
                "avg_iat": c["avg_iat"],
                "num_packets": c["num_packets"]
            })
            
        # Ordenar os eventos cronologicamente
        feed.sort(key=lambda x: x["timestamp"])
        return jsonify(feed)
    except Exception as e:
        print("Erro em terminal_feed:", e)
        return jsonify([])


# ── API JSON para Controlo de Rede ─────────────────────────────
@app.route("/api/network/degrade", methods=["POST"])
@login_required
def api_network_degrade():
    if not docker_client:
        return jsonify({"success": False, "error": "Docker socket indisponível"})
    
    data = request.json
    device = data.get("device")
    delay = data.get("delay", 0)
    loss = data.get("loss", 0)
    
    if not device:
        return jsonify({"success": False, "error": "Dispositivo não especificado"})
        
    try:
        container = docker_client.containers.get(device)
        
        if int(delay) == 0 and int(loss) == 0:
            container.exec_run("tc qdisc del dev eth0 root netem")
            return jsonify({"success": True, "message": f"Restaurado: {device}"})
            
        check = container.exec_run("tc qdisc show dev eth0")
        action = "change" if b"netem" in check.output else "add"
        
        cmd = f"tc qdisc {action} dev eth0 root netem delay {delay}ms loss {loss}%"
        res = container.exec_run(cmd)
        
        return jsonify({
            "success": True, 
            "message": f"Degradação ({delay}ms, {loss}%) aplicada a {device}"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


# ── Página de Análise de Robustez ─────────────────────────────
@app.route("/robustness")
@login_required
def robustness():
    conn = get_db()

    # Confiança média por dispositivo ao longo do tempo (janelas de 60s)
    timeline = conn.execute("""
        SELECT
            CAST(timestamp / 60 AS INTEGER) * 60 AS bucket,
            device_id,
            AVG(confidence) as avg_conf,
            COUNT(*) as n
        FROM classifications
        GROUP BY bucket, device_id
        ORDER BY bucket
    """).fetchall()

    # Estatísticas globais por classe
    class_stats = conn.execute("""
        SELECT
            predicted,
            COUNT(*) as total,
            AVG(confidence) as avg_conf,
            MIN(confidence) as min_conf,
            MAX(confidence) as max_conf,
            AVG(avg_iat) as avg_iat,
            AVG(avg_size) as avg_size
        FROM classifications
        GROUP BY predicted
    """).fetchall()

    conn.close()
    return render_template("robustness.html", timeline=timeline, class_stats=class_stats)


@app.route("/api/robustness/timeline")
@login_required
def api_robustness_timeline():
    conn = get_db()
    rows = conn.execute("""
        SELECT
            CAST(timestamp / 60 AS INTEGER) * 60 AS bucket,
            device_id,
            predicted,
            AVG(confidence) as avg_conf,
            AVG(avg_iat) as avg_iat,
            AVG(avg_size) as avg_size,
            COUNT(*) as n
        FROM classifications
        GROUP BY bucket, device_id
        ORDER BY bucket DESC
        LIMIT 200
    """).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/robustness/export")
@login_required
def api_robustness_export():
    """Exporta todas as classificações como CSV para análise offline."""
    conn = get_db()
    rows = conn.execute("SELECT * FROM classifications ORDER BY timestamp").fetchall()
    conn.close()

    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows([dict(r) for r in rows])

    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode()),
        mimetype="text/csv",
        as_attachment=True,
        download_name="classifications_export.csv"
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)

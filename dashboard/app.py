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
            try:
                raw_rows = conn.execute("SELECT timestamp, src_ip, dst_ip, size FROM raw_packets ORDER BY id DESC LIMIT 40").fetchall()
            except sqlite3.OperationalError:
                # Se a tabela nem existir, ignora
                raw_rows = []
            
        try:
            cls_rows = conn.execute("SELECT timestamp, device_id, predicted, confidence, avg_size, avg_iat, num_packets FROM classifications ORDER BY id DESC LIMIT 20").fetchall()
        except sqlite3.OperationalError:
            cls_rows = []
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
        import traceback
        return jsonify([{
            "type": "packet",
            "timestamp": 9999999999,
            "src_ip": "ERRO",
            "dst_ip": "INTERNO",
            "size": 0,
            "payload_hex": f"ERROR: {str(e)} | Trace: {traceback.format_exc()}",
            "src_port": "ERR",
            "dst_port": "ERR",
            "ttl": "ERR"
        }])


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


@app.route("/api/network/add_device", methods=["POST"])
@login_required
def api_network_add_device():
    if not docker_client:
        return jsonify({"success": False, "error": "Docker socket indisponível"})
    
    data = request.json
    device_type = data.get("type", "telemetry")
    
    map_types = {
        "telemetry": "iot-device-1",
        "event_driven": "iot-device-2",
        "firmware": "iot-device-3"
    }
    base_name = map_types.get(device_type, "iot-device-1")
    
    try:
        base_container = docker_client.containers.get(base_name)
        network_name = list(base_container.attrs['NetworkSettings']['Networks'].keys())[0]
        network = docker_client.networks.get(network_name)
        
        # Encontrar prefixo de IP da rede
        try:
            subnet = network.attrs['IPAM']['Config'][0]['Subnet']
            ip_prefix = subnet.rsplit('.', 1)[0]
        except:
            ip_prefix = "172.20.0"

        max_num = 3
        max_ip_suffix = 12
        
        # Descobrir o ultimo ID e IP em uso
        for c in docker_client.containers.list(all=True):
            if c.name.startswith("iot-device-"):
                try:
                    num = int(c.name.split("-")[-1])
                    if num > max_num:
                        max_num = num
                except:
                    pass
            
            net_settings = c.attrs['NetworkSettings']['Networks']
            if network_name in net_settings:
                ip = net_settings[network_name].get('IPAddress', '')
                if ip.startswith(ip_prefix + "."):
                    try:
                        suffix = int(ip.split(".")[-1])
                        if suffix > max_ip_suffix:
                            max_ip_suffix = suffix
                    except:
                        pass
                        
        next_num = max_num + 1
        next_ip_suffix = max_ip_suffix + 1
        
        device_id = f"device{next_num}"
        container_name = f"iot-device-{next_num}"
        next_ip = f"{ip_prefix}.{next_ip_suffix}"
        
        binds = base_container.attrs['HostConfig'].get('Binds', [])
        
        env = [
            "PYTHONUNBUFFERED=1",
            "BROKER_HOST=broker",
            "BROKER_PORT=8883",
            f"DEVICE_ID={device_id}",
            f"DEVICE_TYPE={device_type}"
        ]
        
        # Herdar as labels do projeto para que o `docker compose down` as consiga apagar
        project_label = base_container.labels.get("com.docker.compose.project", "trabalho")
        container_labels = {
            "com.docker.compose.project": project_label,
            "dynamic_device": "true"
        }
        
        # Criar o contentor (sem ligar à rede automaticamente)
        container = docker_client.containers.create(
            image=base_container.image.id,
            name=container_name,
            environment=env,
            volumes=binds,
            cap_add=["NET_ADMIN"],
            labels=container_labels
        )
        
        # Ligar explicitamente à rede com o IP sequencial desejado
        network.connect(container, ipv4_address=next_ip)
        container.start()
        
        # Formatar display name para a UI
        type_display = "Telemetry"
        if device_type == "event_driven": type_display = "Event-Driven"
        if device_type == "firmware": type_display = "Firmware"
        display_name = f"Device {next_num} — {type_display} ({next_ip})"
        
        return jsonify({
            "success": True, 
            "message": f"Iniciado {container_name} no IP {next_ip}",
            "container_name": container_name,
            "device_id": device_id,
            "display_name": display_name
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
    # ── Limpeza Automática ────────────────────────────────────
    # Apagar dispositivos dinâmicos criados em sessões anteriores
    if docker_client:
        try:
            print("A limpar dispositivos dinâmicos antigos...")
            for c in docker_client.containers.list(all=True):
                if c.name.startswith("iot-device-") and c.name not in ["iot-device-1", "iot-device-2", "iot-device-3"]:
                    print(f"A remover {c.name}...")
                    c.remove(force=True)
        except Exception as e:
            print("Erro ao limpar dispositivos antigos:", e)
            
    app.run(host="0.0.0.0", port=8080, debug=False)

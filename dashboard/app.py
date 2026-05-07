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

IMAGE_MAP = {
    "telemetry":    "pei-iot-device-1",
    "event_driven": "pei-iot-device-2",
    "firmware":     "pei-iot-device-3"
}

def get_host_path(container_name, target_dest):
    """Descobre o caminho no host para um volume bind-mounted."""
    try:
        container = docker_client.containers.get(container_name)
        for m in container.attrs.get("Mounts", []):
            if m["Destination"] == target_dest:
                return m["Source"]
    except:
        pass
    return None

def cleanup_orphans():
    """Remove contentores dinâmicos que ficaram de sessões anteriores."""
    if not docker_client: return
    try:
        # 1. Limpar por label (mais seguro)
        containers = docker_client.containers.list(all=True, filters={"label": "pei-dynamic=true"})
        for c in containers:
            print(f"LIMPANDO (label): Removendo {c.name}")
            try: c.remove(force=True)
            except: pass
            
        # 2. Limpar por padrão de nome (para garantir que só ficam 1, 2 e 3)
        all_c = docker_client.containers.list(all=True)
        for c in all_c:
            if c.name.startswith("iot-device-"):
                try:
                    num = int(c.name.split("-")[-1])
                    if num > 3:
                        print(f"LIMPANDO (nome): Removendo {c.name}")
                        c.remove(force=True)
                except: pass
    except Exception as e:
        print(f"Erro na limpeza: {e}")

# Executar limpeza ao iniciar o dashboard
cleanup_orphans()


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
    # Obter estatísticas da DB
    stats_rows = conn.execute("""
        SELECT device_id, COUNT(*) as count, AVG(confidence) as avg_conf
        FROM classifications GROUP BY device_id
    """).fetchall()
    stats_map = {r['device_id']: r for r in stats_rows}

    conn.close()
    
    # Descobrir dispositivos reais no Docker
    all_devices = []
    running_device_names = []
    if docker_client:
        try:
            for c in docker_client.containers.list():
                if c.name.startswith("iot-device-"):
                    name = c.name
                    running_device_names.append(name)
                    
                    # Obter IP (o classificador usa o IP como device_id na DB)
                    ip = "—"
                    try:
                        networks = c.attrs['NetworkSettings']['Networks']
                        if "pei_iot-net" in networks:
                            ip = networks["pei_iot-net"]["IPAddress"]
                    except: pass
                    
                    # Tentar obter o ID amigável do ambiente ou do nome
                    env_id = None
                    try:
                        for env in c.attrs['Config']['Env']:
                            if env.startswith("DEVICE_ID="):
                                env_id = env.split("=")[1]
                    except: pass
                    friendly_id = env_id or name.replace("iot-", "").replace("-", "")
                    
                    # Na DB o device_id é o IP
                    d_stats = stats_map.get(ip, {"count": 0, "avg_conf": 0})
                    
                    all_devices.append({
                        "id": friendly_id,
                        "name": name,
                        "ip": ip,
                        "count": d_stats["count"],
                        "avg_conf": d_stats["avg_conf"]
                    })
        except:
            pass
            
    # Ordenar por número do dispositivo (device1, device2...)
    def get_device_num(d):
        try: return int(''.join(filter(str.isdigit, d['id'])))
        except: return 999
    all_devices.sort(key=get_device_num)

    return render_template("index.html", 
                         rows=rows, 
                         stats=stats, 
                         devices=all_devices, 
                         running_devices=running_device_names)


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


@app.route("/api/devices/add", methods=["POST"])
@login_required
def api_devices_add():
    if not docker_client:
        return jsonify({"success": False, "error": "Docker socket indisponível"})

    data = request.json
    dtype = data.get("type")
    if dtype not in IMAGE_MAP:
        return jsonify({"success": False, "error": "Tipo de dispositivo inválido"})

    try:
        # Descobrir caminhos no host
        host_data_path = get_host_path("iot-dashboard", "/app/data")
        print(f"DEBUG: host_data_path detectado: {host_data_path}")

        if host_data_path:
            # Se o host for Windows, o dirname do Linux pode falhar com backslashes
            if "\\" in host_data_path:
                host_root = "\\".join(host_data_path.split("\\")[:-1])
                host_certs_path = host_root + "\\certs"
            else:
                host_root = os.path.dirname(host_data_path)
                host_certs_path = os.path.join(host_root, "certs")
            
            print(f"DEBUG: host_certs_path derivado: {host_certs_path}")
        else:
            return jsonify({"success": False, "error": "Não foi possível determinar o caminho do host"})

        # Encontrar um ID e IP livre
        containers = docker_client.containers.list(all=True)
        existing_ids = []
        existing_ips = []
        for c in containers:
            if c.name.startswith("iot-device-"):
                try:
                    num = int(c.name.split("-")[-1])
                    existing_ids.append(num)
                except: pass
                
                # Tentar ler o IP da rede
                networks = c.attrs.get("NetworkSettings", {}).get("Networks", {})
                if "pei_iot-net" in networks:
                    ip = networks["pei_iot-net"].get("IPAddress")
                    if ip:
                        try:
                            last_octet = int(ip.split(".")[-1])
                            existing_ips.append(last_octet)
                        except: pass

        next_id = 1
        while next_id in existing_ids: next_id += 1
        
        # Atribuir IP baseado no ID para ser sequencial (10, 11, 12, 13...)
        next_ip_octet = 9 + next_id
        
        device_id = f"device{next_id}"
        container_name = f"iot-device-{next_id}"
        ip_address = f"172.20.0.{next_ip_octet}"

        # Criar e arrancar o container
        docker_client.containers.run(
            image=IMAGE_MAP[dtype],
            name=container_name,
            detach=True,
            auto_remove=True, # Desaparece ao parar
            network="pei_iot-net",
            cap_add=["NET_ADMIN"],
            labels={
                "com.docker.compose.project": "pei",
                "com.docker.compose.service": "dynamic-device",
                "pei-dynamic": "true"
            },
            environment={
                "PYTHONUNBUFFERED": "1",
                "BROKER_HOST": "broker",
                "BROKER_PORT": "8883",
                "DEVICE_ID": device_id,
                "DEVICE_TYPE": dtype
            },
            volumes={
                host_certs_path: {"bind": "/app/certs", "mode": "ro"},
                host_data_path: {"bind": "/app/data", "mode": "rw"}
            },
            networking_config={
                "pei_iot-net": docker.types.EndpointConfig(
                    docker_client.api._version,
                    ipv4_address=ip_address
                )
            }
        )

        return jsonify({
            "success": True, 
            "message": f"Dispositivo {device_id} adicionado com sucesso (IP: {ip_address})"
        })
    except Exception as e:
        print("Erro ao adicionar dispositivo:", e)
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
    cleanup_orphans()
    app.run(host="0.0.0.0", port=8080, debug=False)

# Tech Stack

## Language
- Python 3 throughout (all services)

## Core Libraries

| Service | Libraries |
|---|---|
| ai-server | `nfstream`, `scikit-learn`, `joblib`, `numpy`, `pandas` |
| dashboard | `flask`, `docker` (SDK) |
| devices | `paho-mqtt`, `ssl`, `json`, `csv` |

## Infrastructure
- **Docker + Docker Compose** — all services run as containers on a private bridge network (`iot-net`, subnet `172.20.0.0/24`)
- **Mosquitto 2.0** — MQTT broker with TLS on port 8883
- **SQLite** — shared database at `/app/data/iot_traffic.db` (WAL mode), mounted as a volume shared between `ai-server` and `dashboard`
- **NFStream** — passive flow capture on `eth0`, BPF filter `tcp port 8883`, `active_timeout=10s`

## ML Models
- Algorithm: `RandomForestClassifier` (scikit-learn), 200 estimators, `class_weight="balanced"`
- Features: `num_packets`, `avg_size`, `std_size`, `avg_iat`, `total_bytes`
- Serialization: `joblib` bundles `{model, features, classes}` → `.joblib` files in `/data`
- Two models: `model.joblib` (3-class) and `binary_model.joblib` (encrypted/non-encrypted)

## Common Commands

```bash
# Start all services (build images if needed)
docker compose up -d --build

# Stop and remove containers
docker compose down

# View logs for a specific service
docker compose logs -f ai-server

# Retrain the multi-class model locally
python ai-server/train.py --csv ./data/self_generated.csv --out ./data/model.joblib

# Retrain the binary model
python ai-server/train_binary.py --csv ./data/self_generated.csv --out ./data/binary_model.joblib

# Regenerate the self-generated dataset
python generate_dataset.py

# Exploratory analysis (generates plots in analysis/plots/)
pip install -r analysis/requirements.txt
python analysis/exploratory_analysis.py

# Robustness experiment (requires running system)
python analysis/robustness_experiment.py --duration 30

# Robustness analysis offline (uses existing DB data)
python analysis/robustness_experiment.py --offline
```

## Networking Notes
- `ai-server` shares the broker's network namespace (`network_mode: "service:broker"`) to see all traffic
- Devices have fixed IPs (`.10`, `.11`, `.12`) — used for identity without payload inspection
- `ai-server` and devices require `NET_ADMIN` / `NET_RAW` capabilities for raw socket and `tc` access

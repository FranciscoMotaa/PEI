# Project Structure

```
.
├── ai-server/          # Passive traffic analyser + ML inference
│   ├── server.py       # Main process: NFStream capture → classify → SQLite
│   ├── train.py        # Train 3-class RandomForest model
│   ├── train_binary.py # Train binary (encrypted/non-encrypted) model
│   └── requirements.txt
│
├── dashboard/          # Flask web UI (port 8080)
│   ├── app.py          # Routes: login, index, /api/* endpoints
│   ├── templates/
│   │   ├── index.html  # Live dashboard
│   │   └── login.html
│   └── requirements.txt
│
├── devices/            # Simulated IoT devices (one folder per device)
│   ├── device1/        # Telemetry — periodic, regular IAT
│   ├── device2/        # Event-driven — sporadic bursts
│   └── device3/        # Firmware — large payload transfers
│
├── data/               # Shared volume: models + SQLite DB + datasets
│   ├── model.joblib         # 3-class traffic model
│   ├── binary_model.joblib  # Encrypted/Non-Encrypted model
│   ├── iot_traffic.db       # SQLite (classifications + raw_packets tables)
│   └── *.csv                # Training datasets
│
├── mosquitto/          # Broker config
│   └── mosquitto.conf
│
├── certs/              # TLS certificates (CA, broker key/cert)
├── captures/           # pcap and flow CSV samples
├── docs/               # Architecture diagrams and reports
│
├── docker-compose.yml  # Orchestrates all services
├── generate_dataset.py # Generates self_generated.csv for training
└── generate_payloads.py
```

## Key Conventions

- Each service is a self-contained folder with its own `Dockerfile` and `requirements.txt`
- The `data/` directory is a shared Docker volume — both `ai-server` and `dashboard` read/write it
- Environment variables drive all runtime config (IPs, paths, passwords, model paths) — no hardcoded values in logic
- Device identity is determined solely by fixed IP address, never by payload content
- SQLite tables: `classifications` (ML results) and `raw_packets` (live packet feed, capped at 300 rows)
- Dashboard API endpoints are all under `/api/` and require session auth (`login_required` decorator)
- Code comments and print log prefixes are written in Portuguese (e.g. `[AI]`, `[DB]`, `[SERVER]`)

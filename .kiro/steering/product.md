# Product Overview

This project is a **passive IoT traffic analysis system** that classifies network traffic from simulated IoT devices using machine learning — without decrypting TLS-encrypted MQTT payloads.

## What it does

- Simulates 3 IoT devices publishing distinct traffic patterns over MQTT/TLS to a Mosquitto broker
- Passively captures network flows using NFStream (transport-layer metadata only: packet sizes, inter-arrival times, IP addresses)
- Classifies traffic into 3 behavioral categories: `telemetry`, `event_driven`, `firmware`
- Also runs a binary classifier: `Encrypted` vs `Non-Encrypted`
- Stores results in a shared SQLite database
- Exposes a Flask web dashboard (password-protected) showing live classifications and raw packet feeds

## Key design principle

The system is a **passive observer** — it never inspects payload content. Device identity is inferred from fixed IP addresses; traffic type is inferred from flow statistics (packet size, IAT, byte counts).

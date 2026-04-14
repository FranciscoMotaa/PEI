# Cria o mesmo Dockerfile nos 3

FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y iproute2 && rm -rf /var/lib/apt/lists/*
RUN pip install paho-mqtt
COPY device.py .
CMD ["python", "device.py"]

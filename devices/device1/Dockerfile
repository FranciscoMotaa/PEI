# Cria o mesmo Dockerfile nos 3

FROM python:3.11-slim
WORKDIR /app
RUN pip install paho-mqtt
COPY device.py .
CMD ["python", "device.py"]

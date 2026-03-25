FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY train.py .
COPY train_binary.py .
COPY server.py .
CMD ["python", "server.py"]
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /code

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts
COPY web ./web

EXPOSE 8080

# 启动: 先 bootstrap 确保安全护栏 (best-effort), 再起 Web
CMD ["sh", "-c", "python -m scripts.bootstrap || true; uvicorn app.api:app --host 0.0.0.0 --port 8080"]

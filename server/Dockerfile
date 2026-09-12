FROM --platform=linux/arm64 python:3.12-slim
WORKDIR /app
COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server ./server
COPY web ./web
ENV VIBEFIND_DATA=/data HF_HOME=/data/hf
EXPOSE 8080
# Non-root; its own /data volume; it can see nothing else on the pi.
RUN useradd -r -u 10001 describesong && mkdir -p /data && chown describesong /data
USER describesong
CMD ["python", "-m", "uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8080"]

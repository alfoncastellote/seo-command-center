FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

COPY . .

RUN mkdir -p /data

EXPOSE 8000

CMD ["python", "worker.py", "serve"]

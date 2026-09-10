FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV HOST=0.0.0.0
ENV PORT=8000

COPY . .

RUN mkdir -p /app/data

EXPOSE 8000

CMD ["sh", "-c", "if [ ! -f /app/data/keywords.json ]; then printf '\\n\\n\\n\\n\\n\\n\\n\\n\\n\\n' | python setup.py; fi && exec python worker.py serve"]

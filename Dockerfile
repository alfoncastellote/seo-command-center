FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV HOST=0.0.0.0
ENV PORT=8000

COPY . .

RUN mkdir -p /app/data \
    && python setup.py
    
EXPOSE 8000

CMD ["python", "worker.py", "serve"]

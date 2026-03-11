FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    python3-dev \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y gcc g++ python3-dev \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

COPY . .

RUN mkdir -p models

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM python:3.10-slim as builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip wheel && pip install --no-cache-dir --user -r requirements.txt

FROM python:3.10-slim as runner

WORKDIR /app

# Install system dependencies for WeasyPrint and PostgreSQL client
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    pango1.0-tools \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /root/.local /root/.local
COPY . .

ENV PATH=/root/.local/bin:$PATH
ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

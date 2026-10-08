FROM python:3.11-slim

# Install system dependencies (Node.js & npm needed by Reflex)
RUN apt-get update && apt-get install -y \
    curl \
    unzip \
    build-essential \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code into container
COPY . .

# Initialize Reflex configuration
RUN reflex init

# Expose ports: FastAPI (8000), Reflex Backend (8002), Reflex UI (3000)
EXPOSE 8000 8002 3000

# Start both FastAPI backend and Reflex app concurrently
CMD ["sh", "-c", "uvicorn api:app --host 0.0.0.0 --port 8000 & reflex run --env prod"]
# Use official lightweight Python image
FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

# Install minimal system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source and configuration files
COPY src/ ./src/
COPY questions/ ./questions/
COPY web_app.py config.yaml ./

# Pre-create runtime directories for outputs and database storage
RUN mkdir -p outputs/reports outputs/json outputs/markdown outputs/csv ledger/backups

# Expose standard Cloud Run port
EXPOSE 8080

# Launch Streamlit dynamically bound to Cloud Run's $PORT
ENTRYPOINT ["sh", "-c", "exec streamlit run web_app.py --server.port=${PORT:-8080} --server.address=0.0.0.0 --server.headless=true --browser.gatherUsageStats=false"]

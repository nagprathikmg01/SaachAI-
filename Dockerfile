FROM python:3.11-slim

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc git curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /code

# Install Python dependencies first (cached layer)
COPY ./backend/requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# Copy entire project
COPY . /code

# Create writable directories for sessions and model
RUN mkdir -p /code/backend/voice_module/model \
    && mkdir -p /data \
    && chmod -R 777 /data

# Hugging Face Spaces expose port 7860
EXPOSE 7860

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s \
    CMD curl -f http://localhost:7860/health || exit 1

# Environment defaults (override with HF Secrets)
ENV PORT=7860
ENV PYTHONPATH=/code
ENV PYTHONUNBUFFERED=1

# Run the server — reads all secrets from HF Space environment variables
CMD ["uvicorn", "backend.server:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]

FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for lxml
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2-dev \
    libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first (better caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY src/ ./src/

# Run as non-root user
RUN useradd -m -u 1000 appuser
USER appuser

# Set Python path
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "weatherfetcher"]

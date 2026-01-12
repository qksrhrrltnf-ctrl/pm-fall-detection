FROM python:3.11-slim

WORKDIR /app

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app ./app

# Create data directory for SQLite
RUN mkdir -p /app/data

# Expose port (Render uses PORT env variable)
EXPOSE 10000

# Run the application with PORT from environment variable
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}

FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY simulate.py .
COPY sample_data ./sample_data

# Default command
CMD ["python", "simulate.py", "--speed", "5", "--minutes", "3"]

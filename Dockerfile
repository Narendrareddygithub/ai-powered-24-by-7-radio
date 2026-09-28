FROM python:3.11-slim

# Install system dependencies (ffmpeg & ca-certificates)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    ca-certificates \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Launch 24/7 radio main broadcast loop
CMD ["python", "main.py"]

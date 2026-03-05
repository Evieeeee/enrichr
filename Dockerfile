FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create temp directories
RUN mkdir -p /tmp/uploads /tmp/outputs

# Cloud Run uses PORT env variable
ENV PORT=8080

# Use gunicorn with threading for background jobs
CMD exec gunicorn \
  --bind 0.0.0.0:$PORT \
  --workers 1 \
  --threads 8 \
  --timeout 0 \
  --worker-class gthread \
  app:app

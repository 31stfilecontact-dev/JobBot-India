# Use official Microsoft Playwright Python base image (includes all OS libraries and Chromium)
FROM mcr.microsoft.com/playwright/python:v1.49.0-noble

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all application source code
COPY . .

# Ensure upload and artifacts directories exist
RUN mkdir -p uploads artifacts/screenshots

# Expose web port
EXPOSE 5000

# Start Flask app using Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "app:app"]

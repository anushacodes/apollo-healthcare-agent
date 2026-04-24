FROM python:3.11-slim

# Install system dependencies required for OpenCV, PyMuPDF, sqlcipher etc.
RUN apt-get update && apt-get install -y \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    sqlite3 \
    libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the project requirements
COPY pyproject.toml .

# Install dependencies
RUN pip install --no-cache-dir .

# Copy the source code
COPY app /app/app
COPY scripts /app/scripts
COPY data /app/data

# Ensure data directories exist
RUN mkdir -p /app/data/patients /app/data/seed /app/data/.cache

# Expose the API port
EXPOSE 8000

# Set environment variables for local testing
ENV PYTHONUNBUFFERED=1

# Start the FastAPI server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

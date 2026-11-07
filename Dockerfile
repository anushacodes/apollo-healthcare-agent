FROM node:24-bookworm-slim AS frontend
WORKDIR /frontend
COPY app/frontend-src/package*.json ./
RUN npm install
COPY app/frontend-src/ ./
RUN npm run build

FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
# Keep the large inference dependencies on CPU in the container.
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --no-cache-dir '.[inference]'
COPY --from=frontend /frontend_dist ./app/frontend_dist
COPY scripts ./scripts
COPY data ./data
COPY knowledge_graph ./knowledge_graph
RUN mkdir -p /app/data/patients /app/data/.cache
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health', timeout=4)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

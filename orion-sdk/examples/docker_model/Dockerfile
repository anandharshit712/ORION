# ORION Docker Model Server — Example Dockerfile
# Replace the base image and dependencies with your own.

FROM python:3.11-slim

WORKDIR /app

# Install dependencies — replace with your own requirements
RUN pip install --no-cache-dir fastapi uvicorn pydantic

# Copy model server and your model code
COPY model_server.py .
# COPY your_model/ ./your_model/  ← add your model files here

# Health check so ORION knows the container is ready
HEALTHCHECK --interval=5s --timeout=3s --retries=5 \
  CMD curl -f http://localhost:8080/health || exit 1

EXPOSE 8080

CMD ["python", "model_server.py"]

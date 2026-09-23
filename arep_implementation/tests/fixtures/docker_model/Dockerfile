# Test fixture image for the container integration test.
#
# No pip install: the server is stdlib-only, so this builds in seconds and
# without network access. The SDK example under orion-sdk/examples/docker_model
# is the one customers copy; this one exists to make the test cheap to run.
FROM python:3.11-slim

WORKDIR /app
COPY server.py .

EXPOSE 8080

# Unbuffered so container logs are useful when a test fails.
ENV PYTHONUNBUFFERED=1

CMD ["python", "server.py"]

# Fast application image - extends pre-built base
# This builds in ~5 seconds since base contains all heavy dependencies
# 
# First time setup:
#   1. Build base: docker build -f Dockerfile.base -t mammothbox-base:latest .
#   2. Build app: docker-compose build
# 
# For code changes (subsequent builds):
#   docker-compose build  (takes ~5 seconds)

FROM mammothbox-base:latest

WORKDIR /app

# Copy application code (only ~1-2MB, very fast)
COPY src/ ./src/
COPY migrations/ ./migrations/
COPY scripts/ ./scripts/

# Expose port
EXPOSE 8000

# Run application
CMD ["python", "-m", "src.main"]


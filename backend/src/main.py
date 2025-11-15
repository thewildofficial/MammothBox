# Main application entry point

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from src.config.settings import get_settings
from src.api.routes import router
from src.queue.manager import get_queue_backend, set_worker_supervisor, reset_queue_backend
from src.queue.supervisor import WorkerSupervisor
from src.queue.processors import JsonJobProcessor, MediaJobProcessor

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan - startup and shutdown."""
    # Startup
    logger.info("Starting worker supervisor...")
    queue_backend = get_queue_backend()

    # Register processors
    processors = {
        "json": JsonJobProcessor(),
        "media": MediaJobProcessor(),  # Placeholder for future
    }

    # Create and start supervisor
    supervisor = WorkerSupervisor(
        queue_backend=queue_backend,
        processors=processors,
        num_workers=settings.worker_threads
    )
    supervisor.start()
    set_worker_supervisor(supervisor)
    logger.info(
        f"Worker supervisor started with {settings.worker_threads} workers")

    yield

    # Shutdown
    logger.info("Stopping worker supervisor...")
    supervisor.stop()
    queue_backend.close()
    # Reset the singleton so subsequent get_queue_backend() calls create a fresh backend
    reset_queue_backend()
    logger.info("Worker supervisor stopped")


app = FastAPI(
    title="Automated File Allocator API",
    description="Smart storage system for media and JSON documents",
    version="0.1.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router, prefix="/api/v1")


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Automated File Allocator API",
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs"
    }


@app.get("/health")
async def health():
    """Health check endpoint (alias for /live)"""
    return {"status": "healthy"}


@app.get("/live")
async def liveness():
    """Liveness check endpoint"""
    return {"status": "alive"}


@app.get("/ready")
async def readiness():
    """Readiness check endpoint"""
    from src.catalog.database import check_database_connection

    db_healthy = check_database_connection()

    return {
        "status": "ready" if db_healthy else "not_ready",
        "database": "connected" if db_healthy else "disconnected"
    }

if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.debug
    )

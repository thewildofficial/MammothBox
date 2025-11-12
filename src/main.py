# Main application entry point

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from src.config.settings import get_settings
from src.api.routes import router

settings = get_settings()

app = FastAPI(
    title="Automated File Allocator API",
    description="Smart storage system for media and JSON documents",
    version="0.1.0"
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

@app.get("/live")
async def liveness():
    """Health check endpoint"""
    return {"status": "alive"}

@app.get("/ready")
async def readiness():
    """Readiness check endpoint"""
    # TODO: Check database connection
    return {"status": "ready"}

if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.debug
    )


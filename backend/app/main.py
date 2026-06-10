from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.auth import router as auth_router
from app.core.config import get_settings
from app.core.ratelimit import limiter

# 1. Initialize the FastAPI instance
app = FastAPI(title="ClipForge API")

# 2. Configure Slowapi Rate Limiting Infrastructure
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# 3. Mount CORS Middleware with split list origins
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 4. Include Application Routers
app.include_router(auth_router, prefix="/api/auth")


# 5. Core Operational Health Endpoint
@app.get("/api/health", tags=["System"])
async def health_check():
    """
    Basic system health check endpoint.
    Used by deployment health probes and verification scripts.
    """
    return {"status": "ok"}
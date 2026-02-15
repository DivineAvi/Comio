import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.config import settings
from apps.api.exceptions import ComioException, comio_exception_handler
from apps.api.routes import auth, health, incidents, projects, sandbox, chat, webhooks
from apps.api.middleware import RequestIDMiddleware
from apps.api.database import engine

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manages application startup and shutdown lifecycle."""

    BANNER = """
      \033[38;5;208m   ██████╗\033[36m ██████╗ ███╗   ███╗██╗ ██████╗
      \033[38;5;208m  ██╔════╝\033[36m██╔═══██╗████╗ ████║██║██╔═══██╗
      \033[38;5;208m  ██║     \033[36m██║   ██║██╔████╔██║██║██║   ██║
      \033[38;5;208m  ██║     \033[36m██║   ██║██║╚██╔╝██║██║██║   ██║
      \033[38;5;208m  ╚██████╗\033[36m╚██████╔╝██║ ╚═╝ ██║██║╚██████╔╝
      \033[38;5;208m   ╚═════╝\033[36m ╚═════╝ ╚═╝     ╚═╝╚═╝ ╚═════╝
      \033[0m\033[90m  Create · Edit · Deploy · Monitor · Fix
       ─────────────────────────────────────────\033[0m
    """

    # --- Startup ---
    print(BANNER)
    logger.info("Comio API v%s starting up...", settings.app_version)
    
    # Initialize event bus
    from events.bus import create_event_bus
    from apps.api.services.event_service import event_service
    
    event_bus = create_event_bus("redis", redis_url=settings.redis_url)
    event_service.set_event_bus(event_bus)
    logger.info("Event bus initialized (Redis)")

    yield  # App runs and handles requests here

    # --- Shutdown ---
    logger.info("Comio API shutting down...")
    
    # Close event bus
    await event_bus.close()
    await event_service.close()
    
    # Close database connections
    await engine.dispose()

def create_app() -> FastAPI:
    """Application factory pattern.

    Why a factory function instead of a global `app = FastAPI()`?
    - Easier to test (create fresh app per test)
    - Can create different configs (test vs dev vs prod)
    - Professional standard in Flask/FastAPI projects
    """

    application = FastAPI(
        title=settings.app_name,
        description="AI-powered platform to create, edit, deploy, and monitor applications.",
        version=settings.app_version,
        lifespan=lifespan,
        docs_url="/docs",   # Swagger UI endpoint
        redoc_url="/redoc", # Swagger UI alternative
    )

    # --- Middleware ---
    # Order matters: middleware is applied in REVERSE order (last added runs first)
    # So CORS runs first (outermost), then RequestID (innermost, closest to your code)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_middleware(RequestIDMiddleware) # Add request ID middleware to every request
    # --- Exception Handlers ---
    application.add_exception_handler(ComioException, comio_exception_handler)

    # --- Routes ---
    application.include_router(health.router, tags=["health"])
    application.include_router(auth.router)        # /auth/register, /auth/login, /auth/refresh, /auth/me
    application.include_router(projects.router)     # /projects/import, /projects/create, etc.
    application.include_router(incidents.router)    # /incidents, /incidents/{id}, approve/reject
    application.include_router(sandbox.router)    # /projects/{id}/sandbox/*
    application.include_router(chat.router)    # /projects/{id}/sandbox/chat/*
    application.include_router(webhooks.router)    # /webhooks/alert, /webhooks/test-alert
    # Future: sandbox, chat, deploy routers will be added here

    return application

# Create the app instance — this is what uvicorn runs
app = create_app()
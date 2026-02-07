import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.config import settings
from apps.api.exceptions import ComioException, comio_exception_handler
from apps.api.routes import health

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
    # Future: initialize DB connection pool, Redis, Docker client

    yield  # App runs and handles requests here

    # --- Shutdown ---
    logger.info("Comio API shutting down...")
    # Future: close DB connections, cleanup resources

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
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # --- Exception Handlers ---
    application.add_exception_handler(ComioException, comio_exception_handler)

    # --- Routes ---
    application.include_router(health.router, tags=["health"])
    # Future: incidents, projects, sandbox, chat, deploy routers will be added here

    return application

# Create the app instance — this is what uvicorn runs
app = create_app()
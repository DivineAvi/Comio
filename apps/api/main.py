import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import RedirectResponse
import re
from urllib.parse import urlparse, parse_qs

from apps.api.config import settings
from apps.api.exceptions import ComioException, comio_exception_handler
from apps.api.routes import auth, health, incidents, projects, sandbox, chat, webhooks, remediations
from apps.api.middleware import RequestIDMiddleware
from apps.api.database import engine
from anomaly_detector import AnomalyWorker
from events.bus import create_event_bus
from apps.api.services.event_service import event_service
from apps.api.services.rca_service import rca_service

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
    event_bus = create_event_bus("redis", redis_url=settings.redis_url)
    event_service.set_event_bus(event_bus)
    logger.info("Event bus initialized (Redis)")
    
    # Initialize RCA service
    rca_service.set_event_bus(event_bus)
    await rca_service.start_subscriber()
    logger.info("RCA service initialized")

    # Initialize Anomaly Detection Worker


    anomaly_worker = AnomalyWorker(
        prometheus_url=settings.prometheus_url,
        redis_url=settings.redis_url,
        event_bus=event_bus,
        check_interval_minutes=5,
        training_lookback_hours=168,  # 1 week
    )
    await anomaly_worker.start()
    logger.info("Anomaly detection worker initialized")

    yield  # App runs and handles requests here

    # --- Shutdown ---
    logger.info("Comio API shutting down...")
    # Close rca service
    await rca_service.close()
    # Close anomaly worker
    await anomaly_worker.stop()
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
    
    @application.middleware("http")
    async def sandbox_proxy_fallback_middleware(request: Request, call_next):
        response = await call_next(request)
        if response.status_code == 404:
            referer = request.headers.get("referer")
            if referer:
                parsed_referer = urlparse(referer)
                match = re.search(r'(/projects/[^/]+/sandbox/proxy/\d+)', parsed_referer.path)
                if match:
                    proxy_base = match.group(1)
                    if not request.url.path.startswith("/projects/"):
                        qs = parse_qs(parsed_referer.query)
                        token = qs.get("token", [""])[0] if "token" in qs else ""
                        
                        # Build redirect URL, preserving the original query string
                        redirect_url = f"{proxy_base}{request.url.path}"
                        
                        redirect_qs = request.url.query
                        if token:
                            if redirect_qs:
                                redirect_qs += f"&token={token}"
                            else:
                                redirect_qs = f"token={token}"
                                
                        if redirect_qs:
                            redirect_url += f"?{redirect_qs}"
                            
                        return RedirectResponse(url=redirect_url, status_code=302)
        return response

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
    application.include_router(remediations.router)  # /remediations (approval workflow)

    return application

# Create the app instance — this is what uvicorn runs
app = create_app()
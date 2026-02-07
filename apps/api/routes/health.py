from fastapi import APIRouter

from apps.api.config import settings

router = APIRouter()

@router.get("/health")
async def health_check():
    """ Health check endpoint 

    Returns service status, name and version.
    Used by Docker, Kubernetes, and load balancers to verify the service is alive.
    """
    return {
        "status": "ok",
        "name": settings.app_name,
        "version": settings.app_version,
    }
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Pydantic's BaseSettings automatically reads from environment variables
    and .env files. This is the single source of truth for all config.
    """

    # App
    app_name: str = "Comio API"
    app_version: str = "0.1.0"
    debug: bool = False

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Database - the connection string for PostgreSQL
    # Format: postgresql+asyncpg://user:password@host:port/dbname
    database_url: str = "postgresql+asyncpg://comio:comio@localhost:5432/comio"

    # Redis - used for caching, rate limiting, pub/sub
    redis_url: str = "redis://localhost:6379/0"

    # Auth
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # CORS - which frontend URLs can call this API
    cors_origins: list[str] = ["http://localhost:3000"]

    # Docker / Sandbox
    docker_host: str = "unix:///var/run/docker.sock"
    sandbox_network: str = "comio-sandbox"
    sandbox_image: str = "comio/sandbox:latest"

    # GitHub
    github_token: str = ""
    github_client_id: str = ""
    github_client_secret: str = ""

    # Deployment
    deploy_domain: str = "comio.dev"           # Base domain for deployed apps
    artifact_registry: str = ""                 # GCP Artifact Registry URL
    gke_cluster: str = ""                       # GKE cluster name
    gke_zone: str = "us-central1-a"             # GKE zone
    gcp_project_id: str = ""                    # GCP project ID

    # LLM Providers
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    default_llm_provider: str = "openai"        # "openai" | "anthropic" | "ollama"
    default_llm_model: str = "gpt-4o"           # Default model for chat/RCA

    model_config = {
        "env_file": ".env",          # Reads from .env file in project root
        "env_file_encoding": "utf-8",
        "case_sensitive": False,      # DATABASE_URL and database_url both work
    }


# Singleton instance — import this wherever you need settings
settings = Settings()
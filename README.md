# Comio

**AI-powered platform to create, edit, deploy, and monitor applications.**

Comio covers the full application lifecycle through a conversational AI interface:

- **Create** — Describe a project in plain English and Comio builds it from scratch
- **Edit** — Chat with an AI assistant that can read, edit, and refactor your code in a sandboxed environment
- **Deploy** — One-click deploy to production with automatic container builds
- **Monitor** — Detects anomalies via ML, diagnoses root causes with LLMs
- **Fix** — Proposes code fixes as PRs with human-in-the-loop approval

## Architecture

```
Frontend (Next.js) → Backend (FastAPI) → AI Engine (LLM Adapters)
                                       → Docker Sandboxes (per-project)
                                       → Observability (Prometheus + Loki)
                                       → GCP (GKE + Terraform)
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16, TypeScript, Tailwind CSS, shadcn/ui |
| Backend | Python 3.12, FastAPI, SQLAlchemy, Alembic |
| Database | PostgreSQL 16 (pgvector), Redis 7 |
| AI Engine | OpenAI, Anthropic, Ollama (provider-agnostic adapter) |
| Sandboxes | Docker containers with AI chat agent (tool-use) |
| Anomaly Detection | scikit-learn, statsmodels, Prophet |
| Observability | OpenTelemetry, Prometheus, Loki, Grafana |
| Infrastructure | GCP (GKE), Terraform, Kubernetes |
| CI/CD | GitHub Actions |

## Project Structure

```
comio/
├── apps/
│   ├── api/              # FastAPI backend
│   ├── web/              # Next.js frontend
│   └── demo-app/         # Demo microservice for testing
├── packages/
│   ├── ai-engine/        # LLM adapters, RCA, fix generation, chat agent
│   ├── anomaly-detector/ # ML-based anomaly detection
│   ├── observability/    # OTel configs, dashboards
│   └── shared/           # Shared types and utilities
├── infra/
│   ├── terraform/        # GCP infrastructure as code
│   ├── k8s/              # Kubernetes manifests
│   └── docker/           # Dockerfiles
├── docker-compose.yml    # Local dev services (Postgres, Redis)
└── .github/workflows/    # CI/CD pipelines
```

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 20+
- Docker Desktop (for Postgres, Redis, and sandboxes)
- Git

### 1. Clone and configure

```bash
git clone https://github.com/your-username/comio.git
cd comio
cp .env.example .env
# Edit .env and add your API keys (OpenAI/Anthropic, GitHub)
```

### 2. Start infrastructure services

```bash
docker compose up -d
```

This starts PostgreSQL (port 5432) and Redis (port 6379).

### 3. Set up the backend

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate    # On Windows: .venv\Scripts\activate
pip install -e .
uvicorn apps.api.main:app --reload --host 0.0.0.0 --port 8000
```

API will be available at `http://localhost:8000`
Interactive docs at `http://localhost:8000/docs`

### 4. Set up the frontend

```bash
cd apps/web
npm install
npm run dev
```

Frontend will be available at `http://localhost:3000`

## Development

### Running linters

```bash
# Python
ruff check apps/api packages/
ruff format apps/api packages/

# Frontend
cd apps/web && npm run lint
```

### Running tests

```bash
# Python
pytest apps/api packages/

# Frontend
cd apps/web && npm test
```

## License

MIT

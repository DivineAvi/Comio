"""Demo e-commerce order API for testing Comio monitoring.

This simulates a simple order service with intentional failure modes
that can be triggered via chaos endpoints.
"""

import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from enum import Enum

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ── Prometheus Metrics ────────────────────────────────

# HTTP request metrics
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"]
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"]
)

# Order-specific metrics
orders_created_total = Counter(
    "orders_created_total",
    "Total number of orders created"
)

orders_total_value = Counter(
    "orders_total_value_dollars",
    "Total value of all orders in dollars"
)

active_chaos_flags = Gauge(
    "active_chaos_flags",
    "Number of active chaos flags",
)

chaos_triggered_total = Counter(
    "chaos_triggered_total",
    "Total number of times chaos was triggered",
    ["chaos_type"]
)

# ── Lifespan ──────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manages application startup and shutdown lifecycle."""
    # Startup
    logger.info("Demo Order API starting up...")
    logger.info("Chaos endpoints available at /chaos/*")
    
    yield  # App runs here
    
    # Shutdown
    logger.info("Demo Order API shutting down...")

# ── Application ───────────────────────────────────────

app = FastAPI(
    title="Demo Order API",
    description="E-commerce order service for Comio monitoring demo",
    version="1.0.0",
    lifespan=lifespan,
)


# ── Middleware: Track HTTP Metrics ───────────────────

@app.middleware("http")
async def prometheus_middleware(request: Request, call_next):
    """Track HTTP request metrics for Prometheus."""
    method = request.method
    path = request.url.path
    
    # Start timer
    start_time = time.time()
    
    # Process request
    response = await call_next(request)
    
    # Calculate duration
    duration = time.time() - start_time
    
    # Record metrics
    http_requests_total.labels(
        method=method,
        endpoint=path,
        status_code=response.status_code
    ).inc()
    
    http_request_duration_seconds.labels(
        method=method,
        endpoint=path
    ).observe(duration)
    
    return response


# ── Models ────────────────────────────────────────────

class OrderStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class OrderItem(BaseModel):
    product_id: str
    quantity: int = Field(gt=0)
    price: float = Field(gt=0)


class CreateOrderRequest(BaseModel):
    customer_id: str
    items: list[OrderItem]


class Order(BaseModel):
    id: str
    customer_id: str
    items: list[OrderItem]
    total: float
    status: OrderStatus
    created_at: str


# ── In-memory storage (simulated database) ────────────

orders_db: dict[str, Order] = {}


# ── Chaos state (global toggles) ──────────────────────

class ChaosState:
    """Global state for chaos engineering toggles."""
    latency_spike_enabled = False
    error_rate_enabled = False
    memory_leak_enabled = False
    cpu_spike_enabled = False
    memory_ballast = []  # For memory leak simulation


chaos = ChaosState()


# ── Helper: Apply chaos effects ───────────────────────

def apply_chaos_effects():
    """Apply chaos effects if enabled (call at start of request)."""
    
    # Latency spike: add 5 second delay
    if chaos.latency_spike_enabled:
        chaos_triggered_total.labels(chaos_type="latency_spike").inc()
        logger.warning("Chaos: Latency spike active (5s delay)")
        time.sleep(5)
    
    # Error rate: 50% chance of failure
    if chaos.error_rate_enabled:
        import random
        if random.random() < 0.5:
            chaos_triggered_total.labels(chaos_type="error_rate").inc()
            logger.error("Chaos: Error rate triggered (500)")
            raise HTTPException(status_code=500, detail="Chaos-induced internal server error")
    
    # Memory leak: allocate 10MB per request
    if chaos.memory_leak_enabled:
        chaos_triggered_total.labels(chaos_type="memory_leak").inc()
        logger.warning("Chaos: Memory leak active (allocating 10MB)")
        chaos.memory_ballast.append(bytearray(10 * 1024 * 1024))
    
    # CPU spike: busy loop for 2 seconds
    if chaos.cpu_spike_enabled:
        chaos_triggered_total.labels(chaos_type="cpu_spike").inc()
        logger.warning("Chaos: CPU spike active (2s busy loop)")
        end_time = time.time() + 2
        while time.time() < end_time:
            _ = sum(range(1000))


# ── API Endpoints ─────────────────────────────────────

@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "demo-order-api",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/metrics")
def metrics():
    """Prometheus metrics endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/orders", response_model=Order, status_code=201)
def create_order(request: CreateOrderRequest):
    """Create a new order."""
    apply_chaos_effects()
    
    # Calculate total
    total = sum(item.price * item.quantity for item in request.items)
    
    # Create order
    order = Order(
        id=str(uuid.uuid4()),
        customer_id=request.customer_id,
        items=request.items,
        total=total,
        status=OrderStatus.PENDING,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    
    orders_db[order.id] = order
    logger.info("Order created: %s (total: $%.2f)", order.id, order.total)
    
    # Track metrics
    orders_created_total.inc()
    orders_total_value.inc(total)
    
    return order


@app.get("/orders/{order_id}", response_model=Order)
def get_order(order_id: str):
    """Get an order by ID."""
    apply_chaos_effects()
    
    order = orders_db.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    
    return order


@app.get("/orders", response_model=list[Order])
def list_orders(customer_id: str | None = None):
    """List all orders (optionally filtered by customer)."""
    apply_chaos_effects()
    
    orders = list(orders_db.values())
    
    if customer_id:
        orders = [o for o in orders if o.customer_id == customer_id]
    
    return orders


# ── Chaos Engineering Endpoints ───────────────────────

def _update_chaos_gauge():
    """Update the chaos flags gauge based on current state."""
    count = sum([
        chaos.latency_spike_enabled,
        chaos.error_rate_enabled,
        chaos.memory_leak_enabled,
        chaos.cpu_spike_enabled,
    ])
    active_chaos_flags.set(count)


@app.post("/chaos/latency-spike")
def enable_latency_spike():
    """Enable latency spike (5s delay on all requests)."""
    chaos.latency_spike_enabled = True
    _update_chaos_gauge()
    logger.warning("Chaos enabled: Latency spike")
    return {"status": "enabled", "effect": "5s delay on all requests"}


@app.post("/chaos/error-rate")
def enable_error_rate():
    """Enable high error rate (50% of requests return 500)."""
    chaos.error_rate_enabled = True
    _update_chaos_gauge()
    logger.warning("Chaos enabled: Error rate")
    return {"status": "enabled", "effect": "50% of requests return 500"}


@app.post("/chaos/memory-leak")
def enable_memory_leak():
    """Enable memory leak (allocates 10MB per request)."""
    chaos.memory_leak_enabled = True
    _update_chaos_gauge()
    logger.warning("Chaos enabled: Memory leak")
    return {"status": "enabled", "effect": "10MB allocated per request"}


@app.post("/chaos/cpu-spike")
def enable_cpu_spike():
    """Enable CPU spike (2s busy loop on each request)."""
    chaos.cpu_spike_enabled = True
    _update_chaos_gauge()
    logger.warning("Chaos enabled: CPU spike")
    return {"status": "enabled", "effect": "2s busy loop per request"}


@app.post("/chaos/reset")
def reset_chaos():
    """Disable all chaos effects and clear memory ballast."""
    chaos.latency_spike_enabled = False
    chaos.error_rate_enabled = False
    chaos.memory_leak_enabled = False
    chaos.cpu_spike_enabled = False
    chaos.memory_ballast.clear()
    _update_chaos_gauge()
    logger.info("All chaos effects disabled")
    return {"status": "reset", "message": "All chaos effects disabled"}


@app.get("/chaos/status")
def get_chaos_status():
    """Get current chaos configuration."""
    return {
        "latency_spike": chaos.latency_spike_enabled,
        "error_rate": chaos.error_rate_enabled,
        "memory_leak": chaos.memory_leak_enabled,
        "cpu_spike": chaos.cpu_spike_enabled,
        "memory_ballast_mb": len(chaos.memory_ballast) * 10,
    }
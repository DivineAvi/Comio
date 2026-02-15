"""Event bus abstraction — publish/subscribe for events.

This is the Strategy Pattern:
- BaseEventBus defines the interface (publish, subscribe)
- RedisEventBus implements it with Redis Pub/Sub
- CloudPubSubEventBus implements it with Google Cloud Pub/Sub (future)

Your application code only talks to the interface, never the concrete class.
Switch from Redis → Cloud Pub/Sub by changing ONE line in the factory.

Architecture:
    Service A: event_bus.publish(topic="alerts", event=AlertEvent(...))
                                    ↓
                            Event Bus (Redis/PubSub)
                                    ↓
    Service B: event_bus.subscribe(topic="alerts", handler=process_alert)
"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import Callable, Awaitable

import redis.asyncio as redis

from .schemas import BaseEvent

logger = logging.getLogger(__name__)

# Type alias for event handlers
EventHandler = Callable[[dict], Awaitable[None]]


class BaseEventBus(ABC):
    """Abstract event bus — all implementations must follow this interface."""

    @abstractmethod
    async def publish(self, topic: str, event: BaseEvent) -> None:
        """Publish an event to a topic.

        Args:
            topic: Topic name, e.g. "alerts.received", "diagnosis.completed"
            event: Event object to publish
        """
        ...

    @abstractmethod
    async def subscribe(self, topic: str, handler: EventHandler) -> None:
        """Subscribe to a topic with a handler function.

        Args:
            topic: Topic name to listen to
            handler: Async function to call when event arrives
                     Handler receives the event dict: handler(event_dict)
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close connections and cleanup resources."""
        ...


class RedisEventBus(BaseEventBus):
    """Redis Pub/Sub implementation of the event bus.

    Uses Redis Pub/Sub channels for event transport.
    Perfect for local development and small-scale deployments.

    Limitations (vs Cloud Pub/Sub):
    - No message durability (if Redis restarts, messages are lost)
    - No delivery guarantees (if subscriber is down, message is missed)
    - No retries or dead-letter queues

    For production scale, migrate to CloudPubSubEventBus.
    """

    def __init__(self, redis_url: str):
        """Initialize Redis connection.

        Args:
            redis_url: Redis connection string, e.g. "redis://localhost:6379/0"
        """
        self._redis_url = redis_url
        self._client: redis.Redis | None = None
        self._pubsub: redis.client.PubSub | None = None
        self._subscriber_tasks: list[asyncio.Task] = []

    async def _ensure_connected(self):
        """Lazy connection — only connect when first needed."""
        if self._client is None:
            self._client = redis.from_url(self._redis_url, decode_responses=True)
            logger.info("Connected to Redis at %s", self._redis_url)

    async def publish(self, topic: str, event: BaseEvent) -> None:
        """Publish event to Redis channel."""
        await self._ensure_connected()

        # Serialize event to JSON
        event_json = json.dumps(event.to_dict())

        # Publish to Redis channel (topic name = channel name)
        await self._client.publish(topic, event_json)

        logger.debug("Published %s to topic '%s'", event.event_type.value, topic)

    async def subscribe(self, topic: str, handler: EventHandler) -> None:
        """Subscribe to a Redis channel and call handler for each message.

        This runs in a background task — it continuously listens for messages
        and calls the handler when they arrive.
        """
        await self._ensure_connected()

        # Create a pubsub instance if we don't have one
        if self._pubsub is None:
            self._pubsub = self._client.pubsub()

        # Subscribe to the channel
        await self._pubsub.subscribe(topic)
        logger.info("Subscribed to topic '%s'", topic)

        # Start background task to listen for messages
        task = asyncio.create_task(self._listen_loop(topic, handler))
        self._subscriber_tasks.append(task)

    async def _listen_loop(self, topic: str, handler: EventHandler):
        """Background loop that reads messages and calls the handler.

        This runs forever (until the app shuts down or an error occurs).
        """
        try:
            async for message in self._pubsub.listen():
                if message["type"] == "message":
                    try:
                        # Deserialize JSON
                        event_dict = json.loads(message["data"])

                        # Call the handler
                        await handler(event_dict)

                    except json.JSONDecodeError:
                        logger.error("Invalid JSON in topic '%s': %s", topic, message["data"])
                    except Exception as e:
                        logger.error("Handler error for topic '%s': %s", topic, e)

        except asyncio.CancelledError:
            logger.info("Subscriber for topic '%s' cancelled", topic)
        except Exception as e:
            logger.error("Listen loop error for topic '%s': %s", topic, e)

    async def close(self) -> None:
        """Close Redis connection and cancel all subscriber tasks."""
        # Cancel all background listeners
        for task in self._subscriber_tasks:
            task.cancel()

        # Wait for them to finish
        if self._subscriber_tasks:
            await asyncio.gather(*self._subscriber_tasks, return_exceptions=True)

        # Close pubsub
        if self._pubsub:
            await self._pubsub.close()

        # Close client
        if self._client:
            await self._client.close()

        logger.info("Redis event bus closed")


class CloudPubSubEventBus(BaseEventBus):
    """Google Cloud Pub/Sub implementation (future).

    This is a stub for production. Implement when deploying to GCP.
    """

    def __init__(self, project_id: str):
        self.project_id = project_id
        raise NotImplementedError("Cloud Pub/Sub support coming Day 24-25 (GCP deployment)")

    async def publish(self, topic: str, event: BaseEvent) -> None:
        raise NotImplementedError()

    async def subscribe(self, topic: str, handler: EventHandler) -> None:
        raise NotImplementedError()

    async def close(self) -> None:
        pass


# ── Factory ───────────────────────────────────────────

def create_event_bus(backend: str = "redis", **kwargs) -> BaseEventBus:
    """Create an event bus instance based on config.

    Args:
        backend: "redis" or "pubsub"
        **kwargs: Backend-specific config (redis_url, project_id, etc.)

    Usage:
        # Development
        event_bus = create_event_bus("redis", redis_url="redis://localhost:6379")

        # Production (future)
        event_bus = create_event_bus("pubsub", project_id="comio-prod")
    """
    if backend == "redis":
        redis_url = kwargs.get("redis_url")
        if not redis_url:
            raise ValueError("redis_url required for Redis event bus")
        return RedisEventBus(redis_url)

    elif backend == "pubsub":
        project_id = kwargs.get("project_id")
        if not project_id:
            raise ValueError("project_id required for Cloud Pub/Sub")
        return CloudPubSubEventBus(project_id)

    else:
        raise ValueError(f"Unknown event bus backend: {backend}")
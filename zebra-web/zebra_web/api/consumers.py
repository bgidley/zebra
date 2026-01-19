"""WebSocket consumers for real-time updates."""

import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)


class WorkflowConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for real-time workflow updates.

    Clients can subscribe to:
    - All updates: join the 'workflows' group
    - Process-specific updates: join 'process_{process_id}' group
    - Definition-specific updates: join 'definition_{definition_id}' group
    """

    async def connect(self):
        """Handle WebSocket connection."""
        self.subscriptions = set()

        # Join the main workflows group by default
        await self.channel_layer.group_add("workflows", self.channel_name)
        self.subscriptions.add("workflows")

        await self.accept()
        logger.info(f"WebSocket connected: {self.channel_name}")

        # Send welcome message
        await self.send(
            text_data=json.dumps(
                {
                    "type": "connected",
                    "message": "Connected to Zebra workflow updates",
                    "channel": self.channel_name,
                }
            )
        )

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        # Leave all groups
        for group in self.subscriptions:
            await self.channel_layer.group_discard(group, self.channel_name)

        logger.info(f"WebSocket disconnected: {self.channel_name}, code: {close_code}")

    async def receive(self, text_data):
        """Handle incoming WebSocket messages.

        Supported commands:
        - subscribe: {"action": "subscribe", "channel": "process_xyz"}
        - unsubscribe: {"action": "unsubscribe", "channel": "process_xyz"}
        - ping: {"action": "ping"}
        """
        try:
            data = json.loads(text_data)
            action = data.get("action")

            if action == "subscribe":
                channel = data.get("channel")
                if channel and channel not in self.subscriptions:
                    await self.channel_layer.group_add(channel, self.channel_name)
                    self.subscriptions.add(channel)
                    await self.send(
                        text_data=json.dumps(
                            {
                                "type": "subscribed",
                                "channel": channel,
                            }
                        )
                    )
                    logger.debug(f"Subscribed to {channel}")

            elif action == "unsubscribe":
                channel = data.get("channel")
                if channel and channel in self.subscriptions and channel != "workflows":
                    await self.channel_layer.group_discard(channel, self.channel_name)
                    self.subscriptions.discard(channel)
                    await self.send(
                        text_data=json.dumps(
                            {
                                "type": "unsubscribed",
                                "channel": channel,
                            }
                        )
                    )
                    logger.debug(f"Unsubscribed from {channel}")

            elif action == "ping":
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "pong",
                        }
                    )
                )

            else:
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "error",
                            "message": f"Unknown action: {action}",
                        }
                    )
                )

        except json.JSONDecodeError:
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "error",
                        "message": "Invalid JSON",
                    }
                )
            )

    # Event handlers for group messages

    async def process_updated(self, event):
        """Handle process update events."""
        await self.send(
            text_data=json.dumps(
                {
                    "type": "process_updated",
                    "process_id": event["process_id"],
                    "state": event["state"],
                    "data": event.get("data"),
                }
            )
        )

    async def task_updated(self, event):
        """Handle task update events."""
        await self.send(
            text_data=json.dumps(
                {
                    "type": "task_updated",
                    "task_id": event["task_id"],
                    "process_id": event["process_id"],
                    "state": event["state"],
                    "data": event.get("data"),
                }
            )
        )

    async def definition_created(self, event):
        """Handle definition creation events."""
        await self.send(
            text_data=json.dumps(
                {
                    "type": "definition_created",
                    "definition_id": event["definition_id"],
                    "name": event["name"],
                }
            )
        )

    async def definition_deleted(self, event):
        """Handle definition deletion events."""
        await self.send(
            text_data=json.dumps(
                {
                    "type": "definition_deleted",
                    "definition_id": event["definition_id"],
                }
            )
        )


# Helper functions for broadcasting events


async def broadcast_process_update(process_id: str, state: str, data: dict = None):
    """Broadcast a process update to all subscribers."""
    from channels.layers import get_channel_layer

    channel_layer = get_channel_layer()

    if channel_layer is None:
        logger.warning("No channel layer configured, skipping broadcast")
        return

    event = {
        "type": "process_updated",
        "process_id": process_id,
        "state": state,
        "data": data,
    }

    # Send to main workflows group
    await channel_layer.group_send("workflows", event)

    # Send to process-specific group
    await channel_layer.group_send(f"process_{process_id}", event)


async def broadcast_task_update(task_id: str, process_id: str, state: str, data: dict = None):
    """Broadcast a task update to all subscribers."""
    from channels.layers import get_channel_layer

    channel_layer = get_channel_layer()

    if channel_layer is None:
        logger.warning("No channel layer configured, skipping broadcast")
        return

    event = {
        "type": "task_updated",
        "task_id": task_id,
        "process_id": process_id,
        "state": state,
        "data": data,
    }

    # Send to main workflows group
    await channel_layer.group_send("workflows", event)

    # Send to process-specific group
    await channel_layer.group_send(f"process_{process_id}", event)


async def broadcast_definition_created(definition_id: str, name: str):
    """Broadcast a definition creation to all subscribers."""
    from channels.layers import get_channel_layer

    channel_layer = get_channel_layer()

    if channel_layer is None:
        return

    await channel_layer.group_send(
        "workflows",
        {
            "type": "definition_created",
            "definition_id": definition_id,
            "name": name,
        },
    )


async def broadcast_definition_deleted(definition_id: str):
    """Broadcast a definition deletion to all subscribers."""
    from channels.layers import get_channel_layer

    channel_layer = get_channel_layer()

    if channel_layer is None:
        return

    await channel_layer.group_send(
        "workflows",
        {
            "type": "definition_deleted",
            "definition_id": definition_id,
        },
    )

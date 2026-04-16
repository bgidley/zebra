"""WebSocket consumers for real-time goal progress updates."""

import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer

from zebra_agent_web.api import agent_engine

logger = logging.getLogger(__name__)


class GoalProgressConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for streaming goal execution progress.

    Clients connect with a run_id and receive progress updates as the
    goal is processed. If the run already completed before connection,
    the final status is sent immediately.
    """

    async def connect(self):
        """Handle WebSocket connection."""
        self.run_id = self.scope["url_route"]["kwargs"]["run_id"]
        self.group_name = f"goal_{self.run_id}"

        # Join the run's channel group
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        logger.debug(f"WebSocket connected for run {self.run_id}")

        # Check if run already exists and send current status
        await self._send_current_status()

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        logger.debug(f"WebSocket disconnected for run {self.run_id}")

    async def receive(self, text_data=None, bytes_data=None):
        """Handle incoming messages (not used but required)."""
        # Clients don't send messages in this protocol
        pass

    async def goal_progress(self, event):
        """
        Handle progress update from channel layer.

        Called when the background task sends a progress update via:
        channel_layer.group_send(group_name, {"type": "goal.progress", "data": {...}})
        """
        await self.send(text_data=json.dumps(event["data"]))

    async def _send_current_status(self):
        """
        Check if run already completed and send status.

        This handles reconnection scenarios where the client connects
        after the run has already finished.
        """
        try:
            await agent_engine.ensure_initialized()
            metrics = agent_engine.get_metrics()

            run = await metrics.get_run(self.run_id)

            if run is not None and run.completed_at is not None:
                # Run already completed - send final status
                if run.success:
                    await self.send(
                        text_data=json.dumps(
                            {
                                "event": "completed",
                                "run_id": run.id,
                                "workflow_name": run.workflow_name,
                                "success": True,
                                "output": str(run.output) if run.output else None,
                                "tokens_used": run.tokens_used,
                            }
                        )
                    )
                else:
                    await self.send(
                        text_data=json.dumps(
                            {
                                "event": "failed",
                                "run_id": run.id,
                                "error": run.error,
                            }
                        )
                    )
            elif run is None:
                # Run not found - either still initializing or invalid ID
                # Send a "pending" status so client knows to wait
                await self.send(
                    text_data=json.dumps(
                        {
                            "event": "pending",
                            "run_id": self.run_id,
                            "message": "Waiting for execution to start...",
                        }
                    )
                )

        except Exception as e:
            logger.exception(f"Error checking run status for {self.run_id}")
            await self.send(
                text_data=json.dumps(
                    {
                        "event": "error",
                        "message": f"Error checking status: {e}",
                    }
                )
            )

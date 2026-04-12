"""
Aurene platform adapter.

Receives messages via HTTP POST from a backend server (Laravel).
Delivers responses via webhook callback to the same server.
Designed for mobile apps where push notifications handle delivery
to the user's device.
"""

import asyncio
import logging
import os
from typing import Dict, Optional, Any

from aiohttp import web

logger = logging.getLogger(__name__)

from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import (
    BasePlatformAdapter,
    MessageEvent,
    MessageType,
    SendResult,
)

AURENE_AVAILABLE = True


def check_aurene_requirements() -> bool:
    return AURENE_AVAILABLE


class AureneAdapter(BasePlatformAdapter):
    """
    Aurene adapter for mobile app backends.

    Inbound: HTTP POST endpoint receives messages from Laravel.
    Outbound: Webhook POST delivers responses back to Laravel.
    """

    MAX_MESSAGE_LENGTH = 4096

    def __init__(self, config: PlatformConfig):
        super().__init__(config, Platform.AURENE)
        self._port = int(os.getenv("AURENE_PORT", "8650"))
        self._webhook_url = os.getenv("AURENE_WEBHOOK_URL", "")
        self._api_key = os.getenv("AURENE_API_KEY", "") or config.token or ""
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._approval_state: Dict[int, str] = {}  # approval_id → session_key
        self._approval_counter = 0

    async def connect(self) -> bool:
        """Start the HTTP server for inbound messages."""
        if not self._webhook_url:
            logger.error("[%s] AURENE_WEBHOOK_URL not configured", self.name)
            return False
        if not self._api_key:
            logger.error("[%s] AURENE_API_KEY not configured", self.name)
            return False

        try:
            self._app = web.Application()
            self._app.router.add_post("/message", self._handle_inbound)
            self._app.router.add_post("/approval", self._handle_approval_callback)
            self._app.router.add_get("/health", self._handle_health)

            self._runner = web.AppRunner(self._app)
            await self._runner.setup()
            site = web.TCPSite(self._runner, "0.0.0.0", self._port)
            await site.start()

            self._mark_connected()
            logger.info("[%s] Aurene adapter listening on 0.0.0.0:%d", self.name, self._port)
            return True
        except Exception as e:
            logger.error("[%s] Failed to start: %s", self.name, e, exc_info=True)
            return False

    async def disconnect(self) -> None:
        """Stop the HTTP server."""
        if self._runner:
            await self._runner.cleanup()
        self._runner = None
        self._app = None
        self._mark_disconnected()
        logger.info("[%s] Disconnected", self.name)

    def _verify_auth(self, request: web.Request) -> bool:
        """Verify the Authorization header matches our API key."""
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:] == self._api_key
        return False

    async def _handle_health(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        return web.json_response({"status": "ok"})

    async def _handle_inbound(self, request: web.Request) -> web.Response:
        """Handle inbound message from Laravel."""
        if not self._verify_auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)

        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)

        chat_id = data.get("chat_id", "")
        user_id = data.get("user_id", "")
        text = data.get("text", "")
        message_id = data.get("message_id", "")

        if not chat_id or not text:
            return web.json_response({"error": "chat_id and text required"}, status=400)

        # Build source for session routing
        source = self.build_source(
            chat_id=str(chat_id),
            chat_name=data.get("chat_name"),
            chat_type="dm",
            user_id=str(user_id) if user_id else str(chat_id),
            user_name=data.get("user_name"),
        )

        # Build message event
        event = MessageEvent(
            text=text,
            message_type=MessageType.TEXT,
            source=source,
            raw_message=data,
            message_id=str(message_id) if message_id else "",
        )

        if not os.getenv("AURENE_HOME_CHANNEL") and chat_id:
            os.environ["AURENE_HOME_CHANNEL"] = str(chat_id)

        # Dispatch asynchronously -- return 200 immediately
        asyncio.create_task(self._process_message(event))

        return web.json_response({"status": "accepted"})

    async def _process_message(self, event: MessageEvent) -> None:
        """Process message through the gateway pipeline."""
        try:
            await self.handle_message(event)
        except Exception as e:
            logger.error("[%s] Error processing message: %s", self.name, e, exc_info=True)

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Deliver a message to Laravel via webhook."""
        if not self._webhook_url:
            return SendResult(success=False, error="No webhook URL configured")

        try:
            import httpx
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    self._webhook_url,
                    json={
                        "chat_id": chat_id,
                        "type": "message",
                        "content": content,
                        "reply_to": reply_to,
                        "metadata": metadata or {},
                    },
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                )
                resp.raise_for_status()
                return SendResult(success=True, message_id=None)
        except Exception as e:
            logger.error("[%s] Webhook delivery failed: %s", self.name, e, exc_info=True)
            return SendResult(success=False, error=str(e))

    async def send_exec_approval(
        self,
        chat_id: str,
        command: str,
        session_key: str,
        description: str = "dangerous command",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Send an approval request to Laravel with button choices.

        Laravel renders the buttons in the mobile app.  When the user taps
        one, Laravel POSTs back to ``/approval`` with the ``approval_id``
        and ``choice``.
        """
        if not self._webhook_url:
            return SendResult(success=False, error="No webhook URL configured")

        self._approval_counter += 1
        approval_id = self._approval_counter

        self._approval_state[approval_id] = session_key

        cmd_preview = command[:3800] + "..." if len(command) > 3800 else command

        try:
            import httpx
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    self._webhook_url,
                    json={
                        "chat_id": chat_id,
                        "type": "approval",
                        "approval_id": approval_id,
                        "command": cmd_preview,
                        "description": description,
                        "buttons": ["once", "session", "always", "deny"],
                        "metadata": metadata or {},
                    },
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                )
                resp.raise_for_status()
                return SendResult(success=True, message_id=str(approval_id))
        except Exception as e:
            # Clean up state so it doesn't leak
            self._approval_state.pop(approval_id, None)
            logger.error("[%s] send_exec_approval failed: %s", self.name, e, exc_info=True)
            return SendResult(success=False, error=str(e))

    async def _handle_approval_callback(self, request: web.Request) -> web.Response:
        """Handle approval button callback from Laravel."""
        if not self._verify_auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)

        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)

        approval_id = data.get("approval_id")
        choice = data.get("choice", "")

        if approval_id is None or choice not in ("once", "session", "always", "deny"):
            return web.json_response(
                {"error": "approval_id and valid choice required"}, status=400,
            )

        try:
            approval_id = int(approval_id)
        except (TypeError, ValueError):
            return web.json_response({"error": "invalid approval_id"}, status=400)

        session_key = self._approval_state.pop(approval_id, None)
        if not session_key:
            return web.json_response(
                {"error": "approval already resolved or unknown"}, status=404,
            )

        from tools.approval import resolve_gateway_approval

        count = resolve_gateway_approval(session_key, choice)
        logger.info(
            "Aurene approval resolved %d approval(s) for session %s (choice=%s, id=%d)",
            count, session_key, choice, approval_id,
        )
        return web.json_response({"status": "resolved", "count": count})

    async def send_typing(self, chat_id: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Send typing indicator via webhook (optional, may be ignored by Laravel)."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    self._webhook_url,
                    json={
                        "chat_id": chat_id,
                        "type": "typing",
                    },
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Accept": "application/json",
                    },
                )
        except Exception:
            pass  # Typing indicators are non-critical

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        """Return basic chat info."""
        return {"name": chat_id, "type": "dm", "chat_id": chat_id}

    def format_message(self, content: str) -> str:
        """Pass through markdown as-is. The mobile app handles rendering."""
        return content

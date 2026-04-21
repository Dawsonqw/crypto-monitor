"""
Feishu (Lark) notifier for crypto-monitor.

Sends text messages, interactive cards, markdown-as-card, and images
to Feishu group chats via the Feishu Open API.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

_DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
_TOKEN_REFRESH_MARGIN = 300  # refresh 5 min before actual expiry


class FeishuNotifier:
    """Async Feishu bot notifier using tenant access token auth."""

    TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    MESSAGE_URL = "https://open.feishu.cn/open-apis/im/v1/messages"
    IMAGE_UPLOAD_URL = "https://open.feishu.cn/open-apis/im/v1/images"

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        receive_id_type: str = "chat_id",
        chat_id: str | None = None,
        proxy_url: str | None = None,
    ) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.receive_id_type = receive_id_type
        self.chat_id = chat_id

        client_kwargs: dict[str, Any] = {"timeout": _DEFAULT_TIMEOUT}
        if proxy_url:
            client_kwargs["proxy"] = proxy_url

        self._client = httpx.AsyncClient(**client_kwargs)

        # Token cache
        self._tenant_token: str | None = None
        self._token_expires_at: float = 0.0

        logger.info(
            "FeishuNotifier initialised (app_id={app_id}, receive_id_type={rid})",
            app_id=app_id,
            rid=receive_id_type,
        )

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    async def _get_tenant_token(self) -> str:
        """Get (or refresh) the tenant access token, with caching."""
        now = time.time()
        if self._tenant_token and now < self._token_expires_at:
            return self._tenant_token

        logger.debug("Requesting new Feishu tenant access token")
        resp = await self._client.post(
            self.TOKEN_URL,
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 0:
            msg = data.get("msg", "unknown error")
            logger.error("Failed to get Feishu token: {msg}", msg=msg)
            raise RuntimeError(f"Feishu token error: {msg}")

        self._tenant_token = data["tenant_access_token"]
        expire_seconds = data.get("expire", 7200)
        self._token_expires_at = now + expire_seconds - _TOKEN_REFRESH_MARGIN

        logger.info(
            "Feishu token acquired, expires in ~{sec}s",
            sec=expire_seconds,
        )
        return self._tenant_token  # type: ignore[return-value]

    async def _auth_headers(self) -> dict[str, str]:
        token = await self._get_tenant_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        }

    # ------------------------------------------------------------------
    # Internal send helper
    # ------------------------------------------------------------------

    async def _send_message(
        self,
        msg_type: str,
        content: str,
        chat_id: str | None = None,
    ) -> dict:
        """Low-level message send."""
        target_id = chat_id or self.chat_id
        if not target_id:
            raise ValueError("No chat_id provided and no default chat_id configured")

        headers = await self._auth_headers()
        payload = {
            "receive_id": target_id,
            "msg_type": msg_type,
            "content": content,
        }

        url = f"{self.MESSAGE_URL}?receive_id_type={self.receive_id_type}"
        logger.debug(
            "Sending {msg_type} message to {target}",
            msg_type=msg_type,
            target=target_id,
        )

        resp = await self._client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 0:
            logger.error("Feishu send failed: {msg}", msg=data.get("msg"))
        else:
            logger.info("Message sent successfully (type={t})", t=msg_type)
        return data

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def send_text(self, text: str, chat_id: str | None = None) -> dict:
        """Send a plain text message."""
        content = json.dumps({"text": text})
        return await self._send_message("text", content, chat_id=chat_id)

    async def send_card(self, card: dict, chat_id: str | None = None) -> dict:
        """Send an interactive card."""
        content = json.dumps(card)
        return await self._send_message("interactive", content, chat_id=chat_id)

    async def send_markdown_as_card(
        self,
        title: str,
        markdown: str,
        chat_id: str | None = None,
    ) -> dict:
        """Convert markdown text into a Feishu interactive card and send it.

        Feishu cards support a subset of markdown via ``lark_md`` elements.
        """
        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"content": title, "tag": "plain_text"},
                "template": "blue",
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": markdown},
                },
            ],
        }
        return await self.send_card(card, chat_id=chat_id)

    async def send_image(
        self, image_path: str, chat_id: str | None = None
    ) -> dict:
        """Upload an image and send it as a message."""
        path = Path(image_path)
        if not path.is_file():
            raise FileNotFoundError(f"Image not found: {image_path}")

        # Step 1: upload image
        token = await self._get_tenant_token()
        upload_headers = {"Authorization": f"Bearer {token}"}

        logger.debug("Uploading image {p}", p=image_path)
        with open(path, "rb") as f:
            resp = await self._client.post(
                self.IMAGE_UPLOAD_URL,
                headers=upload_headers,
                data={"image_type": "message"},
                files={"image": (path.name, f, "image/png")},
            )
        resp.raise_for_status()
        upload_data = resp.json()

        if upload_data.get("code") != 0:
            msg = upload_data.get("msg", "unknown error")
            logger.error("Image upload failed: {msg}", msg=msg)
            raise RuntimeError(f"Feishu image upload error: {msg}")

        image_key = upload_data["data"]["image_key"]
        logger.info("Image uploaded: image_key={k}", k=image_key)

        # Step 2: send image message
        content = json.dumps({"image_key": image_key})
        return await self._send_message("image", content, chat_id=chat_id)

    async def close(self) -> None:
        """Shut down the HTTP client."""
        await self._client.aclose()
        logger.debug("FeishuNotifier HTTP client closed")

"""PersonaPlex WebSocket client."""

import asyncio
import logging
from typing import Optional
from urllib.parse import urlencode

import aiohttp

from .protocol import MessageType, decode_message, encode_audio

logger = logging.getLogger(__name__)


class PersonaPlexClient:
    """Async WebSocket client for PersonaPlex server."""

    def __init__(self, base_url: str):
        """Initialize client.

        Args:
            base_url: Base WebSocket URL (e.g., "wss://localhost:8998/api/chat")
        """
        self.base_url = base_url
        self.session: Optional[aiohttp.ClientSession] = None
        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self.audio_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=100)  # 2s buffer for complete utterances
        self.text_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=50)  # Reasonable limit for text
        self._receive_task: Optional[asyncio.Task] = None

    async def connect(self, text_prompt: str, voice_prompt: str) -> None:
        """Connect to PersonaPlex server and wait for handshake.

        Args:
            text_prompt: Text prompt for the AI
            voice_prompt: Voice prompt filename (e.g., "NATF0.pt")

        Raises:
            RuntimeError: If handshake not received within 60 seconds
            aiohttp.ClientError: If connection fails
        """
        # Build URL with query parameters
        params = {"text_prompt": text_prompt, "voice_prompt": voice_prompt}
        url = f"{self.base_url}?{urlencode(params)}"

        logger.info(f"Connecting to PersonaPlex: {url}")

        # Create session with SSL disabled (self-signed cert)
        ssl_context = aiohttp.TCPConnector(ssl=False)
        self.session = aiohttp.ClientSession(connector=ssl_context)

        # Connect WebSocket
        self.ws = await self.session.ws_connect(url)

        # Wait for handshake with 60-second timeout
        try:
            msg = await asyncio.wait_for(self.ws.receive(), timeout=60)
            if msg.type != aiohttp.WSMsgType.BINARY:
                raise RuntimeError(f"Expected binary handshake, got {msg.type}")

            msg_type, _ = decode_message(msg.data)
            if msg_type != MessageType.HANDSHAKE:
                raise RuntimeError(
                    f"Expected HANDSHAKE (0x00), got {msg_type:02x}"
                )

            logger.info("PersonaPlex handshake received")
        except asyncio.TimeoutError:
            await self.close()
            raise RuntimeError("Handshake timeout (60 seconds)")

        # Start receive loop
        self._receive_task = asyncio.create_task(self._receive_loop())

    async def send_audio(self, opus_bytes: bytes) -> None:
        """Send audio data to server.

        Args:
            opus_bytes: OggOpus encoded audio data
        """
        if not self.ws:
            raise RuntimeError("Not connected")

        message = encode_audio(opus_bytes)
        await self.ws.send_bytes(message)

    async def _receive_loop(self) -> None:
        """Receive loop: routes messages to appropriate queues."""
        try:
            async for msg in self.ws:
                if msg.type == aiohttp.WSMsgType.BINARY:
                    try:
                        msg_type, payload = decode_message(msg.data)

                        if msg_type == MessageType.AUDIO:
                            await self.audio_queue.put(payload)
                        elif msg_type == MessageType.TEXT:
                            text = payload.decode("utf-8")
                            await self.text_queue.put(text)
                        else:
                            logger.warning(f"Unknown message type: {msg_type:02x}")

                    except Exception as e:
                        logger.error(f"Error decoding message: {e}")

                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {self.ws.exception()}")
                    break

                elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED):
                    logger.info("WebSocket closed by server")
                    break

        except Exception as e:
            logger.error(f"Receive loop error: {e}")
        finally:
            logger.info("Receive loop ended")

    async def close(self) -> None:
        """Close connection and clean up resources."""
        logger.info("Closing PersonaPlex client")

        # Cancel receive task
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

        # Close WebSocket
        if self.ws and not self.ws.closed:
            await self.ws.close()

        # Close session
        if self.session and not self.session.closed:
            await self.session.close()

        self.ws = None
        self.session = None
        logger.info("PersonaPlex client closed")

"""PersonaPlex WebSocket protocol implementation.

Message format:
- HANDSHAKE: b"\x00" (sent by server on connect)
- AUDIO: b"\x01" + opus_bytes (bidirectional)
- TEXT: b"\x02" + utf8_text (server to client)
"""

from enum import IntEnum
from typing import Tuple


class MessageType(IntEnum):
    """WebSocket message type identifiers."""
    HANDSHAKE = 0x00
    AUDIO = 0x01
    TEXT = 0x02


def encode_audio(opus_bytes: bytes) -> bytes:
    """Encode audio data for transmission.

    Args:
        opus_bytes: OggOpus encoded audio data

    Returns:
        Message bytes with AUDIO type prefix
    """
    return bytes([MessageType.AUDIO]) + opus_bytes


def decode_message(data: bytes) -> Tuple[MessageType, bytes]:
    """Decode a WebSocket message.

    Args:
        data: Raw message bytes

    Returns:
        Tuple of (message_type, payload_bytes)

    Raises:
        ValueError: If message is empty or has invalid type
    """
    if not data:
        raise ValueError("Empty message")

    msg_type = MessageType(data[0])
    payload = data[1:] if len(data) > 1 else b""

    return msg_type, payload

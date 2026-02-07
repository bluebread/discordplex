"""Audio format conversion between Discord and PersonaPlex."""

import logging
from typing import List, Optional

import numpy as np
import sphn
from scipy import signal

logger = logging.getLogger(__name__)

# Discord: 48kHz stereo int16 PCM, 20ms frames = 1920 samples/ch * 2 ch * 2 bytes = 3840 bytes
# PersonaPlex: 24kHz mono float32, encoded as OggOpus

DISCORD_SAMPLE_RATE = 48000
PERSONAPLEX_SAMPLE_RATE = 24000
DISCORD_CHANNELS = 2
FRAME_DURATION_MS = 20
DISCORD_FRAME_SAMPLES = int(DISCORD_SAMPLE_RATE * FRAME_DURATION_MS / 1000)
PERSONAPLEX_FRAME_SAMPLES = int(PERSONAPLEX_SAMPLE_RATE * FRAME_DURATION_MS / 1000)


class AudioConverter:
    """Converts audio between Discord and PersonaPlex formats."""

    def __init__(self):
        """Initialize converter with Opus stream codecs."""
        # Encoder: 24kHz mono float32 → OggOpus
        self.encoder = sphn.OpusStreamWriter(sample_rate=PERSONAPLEX_SAMPLE_RATE)

        # Decoder: OggOpus → 24kHz mono float32
        self.decoder = sphn.OpusStreamReader(sample_rate=PERSONAPLEX_SAMPLE_RATE)

        # Buffer for PersonaPlex→Discord (Opus frames don't align with 20ms frames)
        self.playback_buffer = np.array([], dtype=np.int16)

    def discord_to_personaplex(self, pcm_bytes: bytes) -> Optional[bytes]:
        """Convert Discord PCM to PersonaPlex OggOpus.

        Args:
            pcm_bytes: Discord PCM data (may be multiple 20ms frames batched together)

        Returns:
            OggOpus bytes, or None if encoder is still buffering
        """
        try:
            # Discord may send batched audio, ensure we have complete frames
            if len(pcm_bytes) % 3840 != 0:
                logger.warning(f"Input size {len(pcm_bytes)} is not a multiple of 3840, truncating")
                pcm_bytes = pcm_bytes[:len(pcm_bytes) // 3840 * 3840]

            if len(pcm_bytes) == 0:
                return None

            # Convert bytes to numpy array
            pcm = np.frombuffer(pcm_bytes, dtype=np.int16)

            # Reshape to (samples, channels)
            pcm = pcm.reshape(-1, DISCORD_CHANNELS)

            # Stereo → mono: average channels
            mono = pcm.mean(axis=1).astype(np.int16)

            # 48kHz → 24kHz: downsample by factor of 2
            downsampled = signal.resample_poly(mono, up=1, down=2)

            # int16 → float32: normalize to [-1, 1]
            float_pcm = downsampled.astype(np.float32) / 32768.0

            # Split into 480-sample frames (20ms at 24kHz) and encode each
            frame_size = PERSONAPLEX_FRAME_SAMPLES  # 480 samples
            opus_chunks = []

            for i in range(0, len(float_pcm), frame_size):
                frame = float_pcm[i:i + frame_size]

                # Skip incomplete frames
                if len(frame) < frame_size:
                    break

                # Encode frame
                self.encoder.append_pcm(frame)
                opus_bytes = self.encoder.read_bytes()

                if opus_bytes:
                    opus_chunks.append(opus_bytes)

            # Return concatenated Opus data (or None if no complete frames)
            return b''.join(opus_chunks) if opus_chunks else None

        except Exception as e:
            logger.error(f"Error in discord_to_personaplex: {e}")
            return None

    def personaplex_to_discord(self, opus_bytes: bytes) -> List[bytes]:
        """Convert PersonaPlex OggOpus to Discord PCM chunks.

        Args:
            opus_bytes: OggOpus encoded audio

        Returns:
            List of 3840-byte PCM chunks (may be empty if buffering)
        """
        try:
            # Decode OggOpus to float32 PCM
            self.decoder.append_bytes(opus_bytes)
            float_pcm = self.decoder.read_pcm()

            if float_pcm is None or len(float_pcm) == 0:
                return []

            # float32 → int16: scale and clip
            int_pcm = np.clip(float_pcm * 32768.0, -32768, 32767).astype(np.int16)

            # 24kHz → 48kHz: upsample by factor of 2 (returns float64)
            upsampled = signal.resample_poly(int_pcm, up=2, down=1)

            # Convert back to int16 (resample_poly returns float64)
            upsampled_int16 = np.clip(upsampled, -32768, 32767).astype(np.int16)

            # Mono → stereo: duplicate channel
            stereo = np.column_stack([upsampled_int16, upsampled_int16])

            # Add to buffer
            self.playback_buffer = np.concatenate([self.playback_buffer, stereo.ravel()])

            # Split into 3840-byte chunks
            chunks = []
            chunk_size = DISCORD_FRAME_SAMPLES * DISCORD_CHANNELS  # 1920 * 2 = 3840 samples

            while len(self.playback_buffer) >= chunk_size:
                chunk = self.playback_buffer[:chunk_size]
                chunks.append(chunk.tobytes())
                self.playback_buffer = self.playback_buffer[chunk_size:]

            return chunks

        except Exception as e:
            logger.error(f"Error in personaplex_to_discord: {e}")
            return []

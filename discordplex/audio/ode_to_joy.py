"""Generate the first two phrases of Ode to Joy as 48kHz stereo int16 PCM."""

import numpy as np

SAMPLE_RATE = 48000

# Note frequencies (Hz)
_NOTES = {
    "C4": 261.63,
    "D4": 293.66,
    "E4": 329.63,
    "F4": 349.23,
    "G4": 392.00,
}

# First two phrases: E E F G | G F E D | C C D E | E- D--
# Each entry is (note_name, duration_in_beats)
_MELODY = [
    ("E4", 1), ("E4", 1), ("F4", 1), ("G4", 1),
    ("G4", 1), ("F4", 1), ("E4", 1), ("D4", 1),
    ("C4", 1), ("C4", 1), ("D4", 1), ("E4", 1),
    ("E4", 1.5), ("D4", 0.5),
    ("D4", 2),
]

BPM = 132
BEAT_DURATION = 60.0 / BPM


def _make_note(freq: float, duration: float) -> np.ndarray:
    """Generate a sine wave with attack/release envelope."""
    n_samples = int(SAMPLE_RATE * duration)
    t = np.arange(n_samples, dtype=np.float64) / SAMPLE_RATE

    # Sine wave
    wave = np.sin(2 * np.pi * freq * t)

    # Attack/release envelope (10ms attack, 30ms release)
    attack_samples = int(SAMPLE_RATE * 0.01)
    release_samples = int(SAMPLE_RATE * 0.03)

    envelope = np.ones(n_samples, dtype=np.float64)
    if attack_samples > 0 and attack_samples < n_samples:
        envelope[:attack_samples] = np.linspace(0, 1, attack_samples)
    if release_samples > 0 and release_samples < n_samples:
        envelope[-release_samples:] = np.linspace(1, 0, release_samples)

    return (wave * envelope * 0.9).astype(np.float32)


def generate_ode_to_joy() -> bytes:
    """Return Ode to Joy as int16 stereo PCM at 48kHz."""
    segments = []
    for note_name, beats in _MELODY:
        freq = _NOTES[note_name]
        duration = beats * BEAT_DURATION
        segments.append(_make_note(freq, duration))

    mono = np.concatenate(segments)

    # Convert to int16
    int16_mono = (mono * 32767).clip(-32768, 32767).astype(np.int16)

    # Stereo: duplicate channel
    stereo = np.column_stack([int16_mono, int16_mono]).flatten()

    return stereo.tobytes()

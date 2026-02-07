# DiscordPlex Implementation Plan

## Context

Build a Discord voice bot that bridges users in a Discord voice channel to a PersonaPlex (Moshi-based) AI server at `localhost:8998`. PersonaPlex is a full-duplex speech-to-speech model. The bot auto-joins when a user enters a voice channel (no explicit commands), supports per-user prompt/voice configuration via prefix commands, and handles concurrency with first-come-first-served.

---

## Key Design Decisions (from user discussion)

- **Auto-join**: Bot listens for `on_voice_state_update` and joins when a user enters any voice channel. Leaves when all users leave.
- **First-come-first-served**: PersonaPlex only supports one session. First user gets it; others are told the bot is busy.
- **Prefix commands**: `!prompt <scenario>`, `!voice <name>`, `!voice-list` — no slash commands.
- **Per-user settings**: `text_prompt` and `voice_prompt` stored in-memory dict keyed by user ID. Defaults: `voice_prompt=NATF0.pt`, `text_prompt="You are a helpful assistant."`.

---

## Protocol Reference (from server.py)

| Item | Detail |
|------|--------|
| Endpoint | `wss://localhost:8998/api/chat?text_prompt=...&voice_prompt=NATF0.pt` |
| Handshake | Wait for server to send `b"\x00"` (takes seconds while processing prompts) |
| Send audio | `b"\x01" + OggOpus page bytes` (via sphn OpusStreamWriter) |
| Recv audio | `b"\x01" + OggOpus bytes` → sphn OpusStreamReader → float32 PCM |
| Recv text | `b"\x02" + UTF-8 bytes` (AI text tokens) |
| Concurrency | Server has `async with self.lock:` — single session only |
| Sample rate | 24kHz mono (Discord is 48kHz stereo) |

---

## Project Structure

```
/root/discordplex/
├── pyproject.toml
├── requirements.txt
├── .env                          # DISCORD_TOKEN, PERSONAPLEX_URL, VOICE_PROMPT_DIR
├── .env.example
├── discordplex/
│   ├── __init__.py
│   ├── __main__.py               # Entry point
│   ├── config.py                 # Settings from env
│   ├── audio/
│   │   ├── __init__.py
│   │   ├── ode_to_joy.py         # Phase 1: generate melody
│   │   ├── source.py             # PCMArraySource + StreamingPlaybackSource
│   │   ├── sink.py               # StreamingSink
│   │   ├── converter.py          # 48kHz stereo ↔ 24kHz mono + sphn Opus
│   │   └── mixer.py              # Phase 3: multi-user mixing
│   ├── personaplex/
│   │   ├── __init__.py
│   │   ├── protocol.py           # Message types + encode/decode
│   │   └── client.py             # aiohttp WebSocket client
│   ├── bot/
│   │   ├── __init__.py
│   │   ├── client.py             # Bot setup + on_voice_state_update
│   │   └── commands.py           # !prompt, !voice, !voice-list
│   └── bridge/
│       ├── __init__.py
│       └── session.py            # Ties Discord ↔ PersonaPlex
```

---

## Dependencies

```
py-cord[voice]>=2.6.0
PyNaCl>=1.5.0
aiohttp>=3.9.0
sphn>=0.1.4,<0.2
scipy>=1.10.0
numpy>=1.24.0
python-dotenv>=1.0
```

System: `apt install ffmpeg libopus-dev libsodium-dev`

---

## Phase 1: Auto-Join + Ode to Joy + Prefix Commands

**Goal**: Bot auto-joins voice channels, plays Ode to Joy as a greeting, and supports `!prompt`, `!voice`, `!voice-list` commands.

### Files to create

1. **`discordplex/config.py`**
   - `DISCORD_TOKEN`, `PERSONAPLEX_URL` (default `wss://localhost:8998/api/chat`), `VOICE_PROMPT_DIR` (path to `.pt` files), `DEFAULT_VOICE` (default `NATF0.pt`), `DEFAULT_PROMPT`.
   - `VOICE_PROMPT_DIR` defaults to the HuggingFace cache path: `/root/.cache/huggingface/hub/models--nvidia--personaplex-7b-v1/snapshots/3343b641d663e4c851120b3575cbdfa4cc33e7fa/voices/`

2. **`discordplex/audio/ode_to_joy.py`**
   - Generate first 2 phrases of Beethoven's 9th (E4 E4 F4 G4 G4 F4 E4 D4 C4 C4 D4 E4 E4-- D4---) using sine waves with attack/release envelope.
   - Returns `bytes` — int16 stereo PCM at 48kHz.

3. **`discordplex/audio/source.py`**
   - `PCMArraySource(AudioSource)`: wraps a pre-generated PCM bytes buffer. `read()` returns 3840-byte chunks (20ms at 48kHz stereo int16). Returns `b''` when exhausted.

4. **`discordplex/bot/commands.py`** — Cog with prefix commands:
   - `!prompt <text>` — Save `text_prompt` for the calling user. Confirm in chat.
   - `!voice <name>` — Validate voice file exists in `VOICE_PROMPT_DIR`, save for user. Confirm in chat.
   - `!voice-list` — Scan `VOICE_PROMPT_DIR` for `*.pt` files, display grouped by prefix (NATF, NATM, VARF, VARM).
   - Per-user settings stored in `bot.user_settings: dict[int, dict]`.

5. **`discordplex/bot/client.py`** — Bot setup:
   - `on_voice_state_update(member, before, after)`: detect user joining/leaving voice channels.
   - On join (user enters a channel, bot not already connected): connect to that channel, play Ode to Joy.
   - On leave (all non-bot users leave the channel): disconnect bot.
   - `active_session: Optional[VoiceSession]` tracks the current session (None = free).
   - `user_settings: dict[int, dict]` stores per-user prompt/voice.

6. **`discordplex/__main__.py`** — Load `.env`, create bot, add commands cog, `bot.run()`.

7. **`.env.example`** — Template with all env vars.

### Auto-join logic (in `client.py`)
```
on_voice_state_update(member, before, after):
  if member is bot: return

  # User joined a voice channel
  if after.channel and (not before.channel or before.channel != after.channel):
    if bot not in any voice channel in this guild:
      connect to after.channel
      play Ode to Joy greeting

  # User left a voice channel
  if before.channel and (not after.channel or before.channel != after.channel):
    if bot is in before.channel and no non-bot members remain:
      disconnect
```

### Verification
- Start bot → user joins voice channel → bot auto-joins, Ode to Joy plays
- `!voice-list` → lists 18 voices in 4 categories
- `!voice NATM0.pt` → confirms voice set
- `!prompt You are a pirate` → confirms prompt set
- User leaves channel → bot disconnects

---

## Phase 2: Bidirectional Audio Bridge (Single User)

**Goal**: User speaks → audio forwarded to PersonaPlex → AI response played back in real-time.

### Architecture
```
Discord (48kHz stereo) → StreamingSink.write()
  → asyncio.Queue → AudioConverter: stereo→mono, 48k→24k, PCM→OggOpus (sphn)
  → PersonaPlex WS: b"\x01" + opus_bytes

PersonaPlex WS: b"\x01" + opus_bytes
  → AudioConverter: OggOpus→PCM (sphn), 24k→48k, mono→stereo
  → asyncio.Queue → StreamingPlaybackSource.read() → Discord
```

### Files to create/modify

1. **`discordplex/personaplex/protocol.py`**
   - `MessageType` enum: HANDSHAKE=0x00, AUDIO=0x01, TEXT=0x02
   - `encode_audio(opus_bytes) → bytes`: prepend 0x01
   - `decode_message(data) → tuple[MessageType, bytes]`: split first byte from payload

2. **`discordplex/personaplex/client.py`** — `PersonaPlexClient`:
   - `connect(text_prompt, voice_prompt)`: open aiohttp WS, wait for handshake (60s timeout)
   - `send_audio(opus_bytes)`: send encoded audio message
   - `receive_loop()`: async loop reading WS, dispatching to `audio_queue` and `text_queue`
   - `close()`: close WS cleanly

3. **`discordplex/audio/converter.py`** — `AudioConverter`:
   - `discord_to_personaplex(pcm_bytes) → Optional[bytes]`: stereo→mono, 48k→24k (resample_poly), int16→float32, sphn OpusStreamWriter, return OggOpus bytes or None if buffering
   - `personaplex_to_discord(opus_bytes) → list[bytes]`: sphn OpusStreamReader, float32→int16, 24k→48k, mono→stereo, split into 3840-byte frames
   - Internal sphn OpusStreamWriter/Reader instances

4. **`discordplex/audio/sink.py`** — `StreamingSink(Sink)`:
   - `write(data, user)`: put PCM bytes into `asyncio.Queue` (drop-oldest if full via `put_nowait` with try/except on full → `get_nowait` + `put_nowait`)

5. **`discordplex/audio/source.py`** — `StreamingPlaybackSource(AudioSource)`:
   - `read()`: pop 3840 bytes from queue, return silence if empty
   - Thread-safe (called from py-cord audio thread)

6. **`discordplex/bridge/session.py`** — `VoiceSession`:
   - `start(voice_client, text_channel, text_prompt, voice_prompt)`: create PersonaPlex client, converter, sink, source, start async loops
   - `_send_loop()`: poll sink queue → converter → PersonaPlex. Send silence when no audio (PersonaPlex expects continuous stream).
   - `_recv_loop()`: poll PersonaPlex audio queue → converter → playback source queue
   - `_text_loop()`: poll PersonaPlex text queue → send to Discord text channel
   - `stop()`: cancel loops, close PersonaPlex, cleanup

7. **`discordplex/bot/client.py`** — Update auto-join:
   - On join: create `VoiceSession` with user's settings, start bridge (replace Ode to Joy with real session)
   - On leave: stop session, mark as free
   - First-come-first-served: if `active_session` is not None, send DM or channel message "Bot is currently in a session with another user."

### Audio conversion details

**Discord → PersonaPlex** (per 20ms frame = 3840 bytes):
1. `np.frombuffer(data, dtype=np.int16).reshape(-1, 2)` → stereo
2. `mono = stereo.mean(axis=1).astype(np.int16)` → 960 samples
3. `resample_poly(mono, up=1, down=2)` → 480 samples at 24kHz
4. `float32 = samples.astype(np.float32) / 32768.0`
5. `opus_writer.append_pcm(float32)` then `opus_writer.read_bytes()`
6. If non-empty: send `b"\x01" + opus_bytes`

**PersonaPlex → Discord** (per WS message):
1. Strip `b"\x01"`, feed to `opus_reader.append_bytes(payload)`
2. `pcm = opus_reader.read_pcm()` → float32 at 24kHz
3. `resample_poly(pcm, up=2, down=1)` → 48kHz
4. `int16 = (pcm * 32767).clip(-32768, 32767).astype(np.int16)`
5. `stereo = np.column_stack([int16, int16]).flatten()` → interleaved
6. Split into 3840-byte chunks, enqueue for playback

### Threading model
- `Sink.write()` and `AudioSource.read()` run on py-cord's thread, not asyncio
- Use `queue.put_nowait()` / `queue.get_nowait()` (thread-safe for non-blocking)
- Send loop: `await asyncio.wait_for(queue.get(), timeout=0.02)` with silence fallback
- Continuous silence when no speakers (PersonaPlex expects uninterrupted audio)

### Verification
1. Start PersonaPlex server
2. Start bot: `python -m discordplex`
3. Set prompt: `!prompt You are a friendly assistant`
4. Join voice channel → bot auto-joins, connects to PersonaPlex
5. Speak → AI responds with audio
6. AI text tokens appear in text channel
7. Leave voice → bot disconnects cleanly

---

## Phase 3: Multi-User Mixing

**Goal**: Multiple users in the same channel; their audio is mixed before sending to PersonaPlex.

### Files to create/modify

1. **`discordplex/audio/mixer.py`** — `AudioMixer`:
   - Per-user queues keyed by user_id
   - `add_audio(user_id, pcm_bytes)`: enqueue audio for user
   - `get_mixed_frame() → bytes`: poll all queues, sum float32 arrays, average by speaker count, clip, return 3840-byte mixed PCM
   - `remove_user(user_id)`: cleanup on leave

2. **`discordplex/audio/sink.py`** — Update `StreamingSink.write(data, user)` to route through mixer instead of single queue.

3. **`discordplex/bridge/session.py`** — `_send_loop` uses `mixer.get_mixed_frame()` on 20ms timer instead of polling single queue.

### Mixing: sum all active PCM (as float32), divide by speaker count, clip to int16 range. Silence if nobody speaking.

### Verification
- Multiple users speaking simultaneously → AI hears coherent mixed audio
- Users joining/leaving mid-session doesn't crash
- AI response heard by all users in channel

---

## Available Voices (18 total)

| Category | Voices |
|----------|--------|
| Natural Female | NATF0, NATF1, NATF2, NATF3 |
| Natural Male | NATM0, NATM1, NATM2, NATM3 |
| Varied Female | VARF0, VARF1, VARF2, VARF3, VARF4 |
| Varied Male | VARM0, VARM1, VARM2, VARM3, VARM4 |

Voice dir: `/root/.cache/huggingface/hub/models--nvidia--personaplex-7b-v1/snapshots/3343b641d663e4c851120b3575cbdfa4cc33e7fa/voices/`

---

## Reference Files

| File | Purpose |
|------|---------|
| `/root/personaplex/moshi/moshi/server.py` | Server protocol (lines 173-251 recv/send, 287 handshake) |
| `/root/personaplex/moshi/moshi/models/loaders.py` | `SAMPLE_RATE=24000`, `FRAME_RATE=12.5` |
| `/root/personaplex/moshi/.venv/lib/python3.12/site-packages/sphn/__init__.pyi` | sphn API |

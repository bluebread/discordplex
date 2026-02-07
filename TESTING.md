# Phase 2 Testing Guide

## Quick Start

### 1. Terminal 1: Start PersonaPlex Server
```bash
cd /root/personaplex/moshi
.venv/bin/python -m moshi.server --ssl ls --host 0.0.0.0
```

Expected output:
```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on https://0.0.0.0:8998
```

### 2. Terminal 2: Start Discord Bot
```bash
cd /root/discordplex-phase2
python3 -m discordplex
```

Expected output:
```
INFO:discordplex.bot.client:DiscordPlex bot ready as YourBotName#1234
```

## Test Scenarios

### Scenario 1: Basic Voice Conversation

**Steps:**
1. In Discord text channel:
   ```
   !prompt You are a helpful coding assistant who speaks concisely
   !voice NATF0.pt
   ```
2. Join a voice channel
3. Wait for bot to join (should be instant)
4. Look for message: "🎙️ Voice session started!"
5. Speak: "Hello, can you hear me?"
6. Listen for AI response in voice
7. Watch text channel for AI text output: "🤖 AI: Yes, I can hear you!"

**Expected Results:**
- Bot joins within 1 second
- Session start message appears
- Voice response within 200-500ms of speaking
- Text appears in chunks as AI speaks
- Clean audio without glitches or dropouts

**Troubleshooting:**
- No bot join? Check DISCORD_TOKEN in .env
- No voice? Check PersonaPlex server is running
- WebSocket error? Check PERSONAPLEX_URL matches server URL
- No text output? Check bot has permission to send messages in channel

---

### Scenario 2: Custom Voice Personality

**Steps:**
1. In Discord text channel:
   ```
   !prompt You are a pirate captain searching for treasure. Speak like a pirate and be enthusiastic about gold!
   !voice NATM2.pt
   ```
2. Join voice channel
3. Speak: "What are you looking for today?"
4. Observe pirate-themed response

**Expected Results:**
- AI uses pirate vocabulary and grammar
- Male voice (NATM2.pt)
- Enthusiastic tone about treasure/gold

---

### Scenario 3: Session Concurrency Test

**Steps:**
1. User A: Join voice channel
2. Wait for session to start
3. User B: Join same voice channel
4. Check User B sees: "Bot is currently in a session with another user"
5. User A: Leave channel
6. Wait for bot to disconnect
7. User B: Leave and rejoin
8. Check new session starts for User B

**Expected Results:**
- Only one user can have active session
- Second user gets clear message
- Session properly releases when first user leaves
- New session starts immediately when retry

---

### Scenario 4: Long Conversation Test

**Steps:**
1. Start voice session
2. Have 10+ back-and-forth exchanges
3. Monitor for:
   - Audio quality degradation
   - Latency increase
   - Memory leaks (use `htop` to monitor bot process)
   - Queue overflow warnings in logs

**Expected Results:**
- Consistent audio quality throughout
- Latency stays <500ms
- Memory usage stable (or grows slowly)
- No queue overflow warnings

---

### Scenario 5: Error Recovery

**Steps:**
1. Start voice session
2. In PersonaPlex terminal: Ctrl+C to kill server
3. Observe bot behavior
4. Check for error message in Discord
5. Restart PersonaPlex server
6. Leave and rejoin voice channel
7. Verify new session starts

**Expected Results:**
- Bot detects WebSocket closure
- Error message sent to Discord: "❌ Audio send error: ..."
- Bot stops cleanly (no zombie processes)
- New session works after restart

---

### Scenario 6: Voice Switching

**Steps:**
1. Start session with NATF0.pt
2. Leave voice channel
3. In text channel: `!voice VARM4.pt`
4. Rejoin voice channel
5. Verify new voice is used

**Expected Results:**
- Settings persist between sessions
- Voice changes correctly
- No conflicts or errors

---

## Monitoring Commands

### Check bot logs
```bash
# In Terminal 2 (where bot is running)
# Look for these log messages:
# - "Joined voice channel: ..."
# - "PersonaPlex handshake received"
# - "Voice session started"
# - Any WARNING or ERROR messages
```

### Check PersonaPlex server logs
```bash
# In Terminal 1 (where server is running)
# Look for:
# - WebSocket connection messages
# - Audio frame processing
# - Any errors or timeouts
```

### Monitor system resources
```bash
# In Terminal 3
htop
# Look for:
# - python3 processes (bot and server)
# - CPU usage (should be <50% per core)
# - Memory usage (stable, not growing rapidly)
```

## Common Issues

### Issue: "Handshake timeout (60 seconds)"
**Cause:** PersonaPlex server not responding or wrong URL
**Fix:**
- Check server is running: `ps aux | grep moshi.server`
- Check URL in .env matches server: `wss://localhost:8998/api/chat`
- Try `telnet localhost 8998` to verify server is listening

### Issue: "Audio send error" or "Audio receive error"
**Cause:** WebSocket closed or network issue
**Fix:**
- Check PersonaPlex server logs for errors
- Restart both server and bot
- Check firewall isn't blocking localhost connections

### Issue: No voice output in Discord
**Cause:** Playback queue empty or audio conversion issue
**Fix:**
- Check bot logs for "Audio receive error"
- Verify PersonaPlex is sending audio (check server logs)
- Try different voice prompt

### Issue: "Bot is currently in a session" but no one in voice
**Cause:** Session didn't clean up properly
**Fix:**
- Restart bot
- Check logs for cleanup errors
- If persistent, check for zombie tasks: `ps aux | grep python`

### Issue: Text output appears but no voice
**Cause:** PersonaPlex sending text but not audio, or playback issue
**Fix:**
- Check if audio frames being received (check bot logs)
- Verify Discord voice permissions
- Try leaving and rejoining voice channel

## Success Metrics

After testing, verify:
- ✓ Voice sessions start within 2 seconds of joining
- ✓ Audio latency < 500ms (ideally 200-300ms)
- ✓ No audio glitches or dropouts during 5+ minute conversation
- ✓ Text output appears in near real-time
- ✓ Concurrent session blocking works correctly
- ✓ Clean shutdown with no resource leaks
- ✓ Error recovery works (can reconnect after failures)
- ✓ Voice switching between sessions works

## Performance Benchmarks

Typical metrics on a modern system:
- Connection time: 500-1000ms
- Handshake time: 50-200ms
- Audio latency (user speech → AI response): 200-400ms
- Text latency (AI starts speaking → text appears): <100ms
- Memory usage (bot): 100-200 MB
- Memory usage (PersonaPlex server): 2-4 GB (GPU memory)
- CPU usage (bot): 5-15% of one core
- CPU usage (server): 30-60% (with GPU acceleration)

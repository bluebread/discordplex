import os

from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN: str = os.environ["DISCORD_TOKEN"]

PERSONAPLEX_URL: str = os.getenv(
    "PERSONAPLEX_URL", "wss://localhost:8998/api/chat"
)

VOICE_PROMPT_DIR: str = os.getenv(
    "VOICE_PROMPT_DIR",
    "/root/.cache/huggingface/hub/models--nvidia--personaplex-7b-v1"
    "/snapshots/3343b641d663e4c851120b3575cbdfa4cc33e7fa/voices/",
)

DEFAULT_VOICE: str = "NATF0.pt"

DEFAULT_PROMPT: str = "You are a helpful assistant."

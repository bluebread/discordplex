"""Entry point for DiscordPlex bot."""

import logging

import discord

from discordplex.config import DISCORD_TOKEN
from discordplex.bot.client import create_bot
from discordplex.bot.commands import VoiceCommands


log = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if not discord.opus.is_loaded():
        discord.opus._load_default()
        log.info("Loaded opus: %s", discord.opus.is_loaded())

    bot = create_bot()
    bot.add_cog(VoiceCommands(bot))
    bot.run(DISCORD_TOKEN)


if __name__ == "__main__":
    main()

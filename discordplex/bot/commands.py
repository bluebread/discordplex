"""Prefix commands for DiscordPlex bot."""

import os
from pathlib import Path

import discord
from discord.ext import commands

from discordplex.config import DEFAULT_PROMPT, DEFAULT_VOICE, VOICE_PROMPT_DIR


class VoiceCommands(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="prompt")
    async def set_prompt(self, ctx: commands.Context, *, text: str) -> None:
        """Set your text prompt for the AI. Usage: !prompt <scenario>"""
        uid = ctx.author.id
        settings = self.bot.user_settings.setdefault(uid, {})
        settings["text_prompt"] = text
        await ctx.reply(f"Prompt set to: {text}")

    @commands.command(name="voice")
    async def set_voice(self, ctx: commands.Context, name: str) -> None:
        """Set your voice. Usage: !voice <name> (e.g. NATF0.pt)"""
        # Ensure .pt extension
        if not name.endswith(".pt"):
            name += ".pt"

        voice_path = Path(VOICE_PROMPT_DIR) / name
        if not voice_path.exists():
            await ctx.reply(f"Voice `{name}` not found. Use `!voice-list` to see available voices.")
            return

        uid = ctx.author.id
        settings = self.bot.user_settings.setdefault(uid, {})
        settings["voice_prompt"] = name
        await ctx.reply(f"Voice set to: {name}")

    @commands.command(name="voice-list")
    async def voice_list(self, ctx: commands.Context) -> None:
        """List available voices grouped by category."""
        voice_dir = Path(VOICE_PROMPT_DIR)
        if not voice_dir.is_dir():
            await ctx.reply("Voice directory not found.")
            return

        voices = sorted(f.name for f in voice_dir.glob("*.pt"))
        if not voices:
            await ctx.reply("No voice files found.")
            return

        # Group by prefix
        categories: dict[str, list[str]] = {}
        labels = {
            "NATF": "Natural Female",
            "NATM": "Natural Male",
            "VARF": "Varied Female",
            "VARM": "Varied Male",
        }
        for v in voices:
            prefix = v[:4]
            categories.setdefault(prefix, []).append(v)

        lines = [f"**Available Voices ({len(voices)} total)**\n"]
        for prefix, label in labels.items():
            group = categories.get(prefix, [])
            if group:
                names = ", ".join(f"`{n}`" for n in group)
                lines.append(f"**{label}**: {names}")

        # Any uncategorized
        known = set(labels.keys())
        for prefix, group in categories.items():
            if prefix not in known:
                names = ", ".join(f"`{n}`" for n in group)
                lines.append(f"**{prefix}**: {names}")

        await ctx.reply("\n".join(lines))


def setup(bot: commands.Bot) -> None:
    bot.add_cog(VoiceCommands(bot))

"""LLM cog — Nito speaks. Persona from persona.md, associative memory, recent turns.
Opt-in: only registers when config.llm.enabled is true and a base_url is set."""
import os
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from config import DATA
from llm import LLMClient, build_messages
from memory import MemoryStore

_PERSONA_FALLBACK = "You are Nito: quiet, polite, brief. No emojis. Be honest and kind."


def _persona() -> str:
    p = Path("persona.md")
    return p.read_text(encoding="utf-8") if p.exists() else _PERSONA_FALLBACK


class LLM(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        cfg = bot.cfg.get("llm", {})
        self.client = LLMClient(cfg.get("base_url", ""), cfg.get("model", ""),
                                os.environ.get(cfg.get("api_key_env", "NITOBOT_LLM_KEY"), ""))
        self.persona = _persona()
        DATA.mkdir(parents=True, exist_ok=True)
        self.mem = MemoryStore(str(DATA / "memory.db"))
        self.history = {}   # channel_id -> recent [{role, content}]

    async def _respond(self, channel_id, scope, text: str) -> str:
        memories = self.mem.recall(scope, text, k=3)
        hist = self.history.get(channel_id, [])[-6:]
        reply = await self.client.chat(build_messages(self.persona, memories, hist, text))
        turns = self.history.setdefault(channel_id, [])
        turns += [{"role": "user", "content": text}, {"role": "assistant", "content": reply}]
        self.history[channel_id] = turns[-12:]
        self.mem.remember(scope, f"{text} -> {reply}")
        return reply

    @app_commands.command(description="Ask Nito something.")
    async def ask(self, interaction: discord.Interaction, prompt: str):
        await interaction.response.defer(thinking=True)
        try:
            reply = await self._respond(interaction.channel_id,
                                        f"{interaction.guild_id}:{interaction.user.id}", prompt)
        except Exception:
            await interaction.followup.send("i couldn't reach my thoughts just now.")
            return
        await interaction.followup.send(reply[:1900] or "…")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild or self.bot.user not in message.mentions:
            return
        text = message.content.replace(f"<@{self.bot.user.id}>", "").replace(f"<@!{self.bot.user.id}>", "").strip()
        if not text:
            return
        async with message.channel.typing():
            try:
                reply = await self._respond(message.channel.id, f"{message.guild.id}:{message.author.id}", text)
            except Exception:
                return
        await message.reply(reply[:1900] or "…", mention_author=False)


async def setup(bot):
    cfg = bot.cfg.get("llm", {})
    if not cfg.get("enabled") or not cfg.get("base_url"):
        return  # disabled / unconfigured -> stay silent, register nothing
    await bot.add_cog(LLM(bot))

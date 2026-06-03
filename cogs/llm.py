"""LLM/agent cog — Nito speaks and acts.

She replies on @mention or /ask, with persona (persona.md) + holographic memory, and is
*agentic*: via OpenAI-compatible tool calling she can look up balances/leaderboards/memory
for anyone, and perform moderation (timeout/purge/slowmode) ONLY when an admin asks — every
admin tool is gated both in agent.dispatch and by Discord permission/hierarchy guards here.
Opt-in: registers only when llm.enabled + base_url are set."""
import datetime
import os
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from agent import run_agent, ToolContext
from config import DATA
from llm import LLMClient, build_messages
from memory import MemoryStore
from modutil import can_moderate
from nito import nito_str

_PERSONA_FALLBACK = "You are Nito: quiet, polite, brief. No emojis. Be honest and kind."
_MOD_PERMS = ("moderate_members", "kick_members", "ban_members", "manage_messages")


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
        self.history = {}

    def _context(self, guild, channel, requester) -> ToolContext:
        perms = getattr(requester, "guild_permissions", None)
        is_admin = bool(perms and any(getattr(perms, p) for p in _MOD_PERMS))

        async def get_balance(user_id):
            return nito_str(self.bot.economy.balance(int(user_id)))

        async def leaderboard():
            rows = self.bot.economy.leaderboard(10)
            return ", ".join(f"<@{u}>={nito_str(b)}" for u, b in rows) or "no one has earned yet"

        async def recall_memory(query):
            return " | ".join(self.mem.recall(f"{guild.id}:{requester.id}", query, k=3)) or "nothing relevant"

        async def timeout_member(user_id, minutes, reason="—"):
            member = guild.get_member(int(user_id))
            if member is None:
                return "no such member here"
            ok, why = can_moderate(requester.top_role.position, member.top_role.position,
                                   guild.me.top_role.position,
                                   actor_has_perm=requester.guild_permissions.moderate_members,
                                   target_is_self=member.id == requester.id,
                                   target_is_owner=member.id == guild.owner_id)
            if not ok:
                return f"refused: {why}"
            mins = max(1, min(int(minutes), 40320))
            await member.timeout(discord.utils.utcnow() + datetime.timedelta(minutes=mins),
                                 reason=f"{requester} via Nito: {reason}"[:400])
            return f"timed out {member} for {mins} min"

        async def purge_messages(count):
            if not requester.guild_permissions.manage_messages:
                return "refused: requester lacks manage_messages"
            deleted = await channel.purge(limit=max(1, min(int(count), 100)))
            return f"deleted {len(deleted)} messages"

        async def set_slowmode(seconds):
            if not requester.guild_permissions.manage_channels:
                return "refused: requester lacks manage_channels"
            await channel.edit(slowmode_delay=max(0, min(int(seconds), 21600)))
            return f"slowmode set to {seconds}s"

        return ToolContext(is_admin, {
            "get_balance": get_balance, "leaderboard": leaderboard, "recall_memory": recall_memory,
            "timeout_member": timeout_member, "purge_messages": purge_messages, "set_slowmode": set_slowmode})

    async def _respond(self, guild, channel, requester, mentions, text: str) -> str:
        scope = f"{guild.id}:{requester.id}"
        roster = ", ".join(f"{m.display_name}={m.id}" for m in ([requester] + list(mentions)))
        sys_extra = (f"{self.persona}\nYou are in a Discord server. Requester is "
                     f"{'an admin' if self._context(guild, channel, requester).is_admin else 'a regular member'}. "
                     f"Members in scope (name=id): {roster}. Use tools when useful; never claim to have "
                     f"acted unless a tool confirmed it.")
        hist = self.history.get(channel.id, [])[-6:]
        messages = build_messages(sys_extra, self.mem.recall(scope, text, k=3), hist, text)
        reply = await run_agent(self.client, messages, self._context(guild, channel, requester))
        turns = self.history.setdefault(channel.id, [])
        turns += [{"role": "user", "content": text}, {"role": "assistant", "content": reply}]
        self.history[channel.id] = turns[-12:]
        self.mem.remember(scope, f"{text} -> {reply}")
        return reply

    @app_commands.command(description="Ask Nito something (she can also act for admins).")
    @app_commands.guild_only()
    async def ask(self, interaction: discord.Interaction, prompt: str):
        await interaction.response.defer(thinking=True)
        try:
            reply = await self._respond(interaction.guild, interaction.channel, interaction.user, [], prompt)
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
        others = [m for m in message.mentions if m.id != self.bot.user.id]
        async with message.channel.typing():
            try:
                reply = await self._respond(message.guild, message.channel, message.author, others, text)
            except Exception:
                return
        await message.reply(reply[:1900] or "…", mention_author=False)


async def setup(bot):
    cfg = bot.cfg.get("llm", {})
    if not cfg.get("enabled") or not cfg.get("base_url"):
        return
    await bot.add_cog(LLM(bot))

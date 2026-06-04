"""Knowledge cog — wires Irminsul into NitoBot. It remembers what people write (per guild),
consolidates it into Irminsul's bounded knowledge tree on a periodic loop, and exposes the
engine as ``bot.knowledge`` so the LLM cog can inject an Akasha knowledge card.

Heavy work (HDC encode + sqlite + grow) runs in a thread executor so it never blocks Discord's
event loop. Errors are swallowed: knowledge is best-effort and must never break the bot."""
import asyncio

import discord
from discord.ext import commands, tasks

_MIN_LEN = 8                # ignore trivial messages
_GROW_MINUTES = 30


class KnowledgeCog(commands.Cog):
    def __init__(self, bot, knowledge):
        self.bot = bot
        self.k = knowledge
        bot.knowledge = self.k                 # the LLM cog reads this if present
        self._active = set()
        self.grow_loop.start()

    def cog_unload(self):
        self.grow_loop.cancel()
        self.k.close()

    async def _run(self, fn, *args):
        try:
            return await asyncio.get_event_loop().run_in_executor(None, fn, *args)
        except Exception:
            return None

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        text = (message.content or "").strip()
        if len(text) < _MIN_LEN:
            return
        scope = Knowledge.scope_for(message.guild.id)
        self._active.add(scope)
        await self._run(self.k.remember, text, scope)     # off the event loop

    @tasks.loop(minutes=_GROW_MINUTES)
    async def grow_loop(self):
        for scope in list(self._active):
            await self._run(self.k.grow, scope)

    @grow_loop.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    if not bot.cfg.get("irminsul", {}).get("enabled", True):
        return
    try:
        from knowledge import Knowledge          # pulls in irminsul (AGPL-3.0)
    except ImportError:
        print("knowledge cog: irminsul not installed — knowledge/Akasha disabled. "
              "Install `irminsul` (AGPL-3.0) to enable it.")
        return
    await bot.add_cog(KnowledgeCog(bot, Knowledge(bot.cfg)))

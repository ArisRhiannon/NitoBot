"""Earn cog: the only source of Nito. Counts messages, commits each epoch, and
gossips the signed attestation to peer NitoBots so earnings can be corroborated."""
import time

import discord
from discord.ext import commands, tasks

from economy import EPOCH_SECONDS


class Earn(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.flush.start()

    def cog_unload(self):
        self.flush.cancel()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        self.bot.economy.record(message.channel.id, message.author.id, message.id, ts=time.time())

    @tasks.loop(seconds=60)
    async def flush(self):
        """Seal epochs whose window has closed and gossip our attestation to peers."""
        econ = self.bot.economy
        now = time.time()
        for epoch in list(econ._pending.keys()):
            idx = int(epoch.rsplit(":", 1)[1])
            if now >= (idx + 1) * EPOCH_SECONDS:        # window closed -> commit it
                att = econ.seal(epoch)
                econ._pending.pop(epoch, None)
                if att:
                    await self.bot.gossip.publish(att)  # corroborate with peer NitoBots

    @flush.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Earn(bot))

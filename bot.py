"""NitoBot entrypoint. Minimal core: a shared Economy + a registry of cogs.

Run:  NITOBOT_TOKEN=... python3 bot.py      (after `python3 install.py`)
"""
import asyncio

import discord
from discord.ext import commands

import config
from economy import Economy


class NitoBot(commands.Bot):
    def __init__(self, cfg: dict):
        intents = discord.Intents.default()
        intents.message_content = True  # required to count what users write
        super().__init__(command_prefix="!", intents=intents, help_command=None)
        self.cfg = cfg
        self.economy = Economy(config.load_instance(), quorum=cfg["quorum"])

    async def setup_hook(self):
        for name in self.cfg["modules"]:
            await self.load_extension(f"cogs.{name}")
        await self.tree.sync()  # register slash commands

    async def on_ready(self):
        print(f"Nito is online as {self.user} ({len(self.guilds)} guild(s)).")


def main():
    cfg = config.load_config()
    NitoBot(cfg).run(config.token())


if __name__ == "__main__":
    main()

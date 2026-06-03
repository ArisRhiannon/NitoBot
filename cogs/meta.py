import discord
from discord import app_commands
from discord.ext import commands


class Meta(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(description="Check that Nito is awake.")
    async def ping(self, interaction: discord.Interaction):
        ms = round(self.bot.latency * 1000)
        await interaction.response.send_message(f"I'm here. {ms} ms.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Meta(bot))

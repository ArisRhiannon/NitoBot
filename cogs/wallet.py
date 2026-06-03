"""Wallet cog: a NitoWallet keyed to the absolute Discord user ID. Balance is the
corroborated earnings + net transfers; the only way to gain Nito is to write."""
import discord
from discord import app_commands
from discord.ext import commands

from nito import NitoError, nito_str


class Wallet(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(description="Show your NitoWallet balance (or someone else's).")
    async def balance(self, interaction: discord.Interaction, user: discord.User = None):
        who = user or interaction.user
        bal = self.bot.economy.balance(who.id)
        await interaction.response.send_message(f"{who.display_name}: {nito_str(bal)}", ephemeral=True)

    @app_commands.command(description="Send Nito to another member.")
    async def pay(self, interaction: discord.Interaction, user: discord.User, nitters: int):
        try:
            self.bot.economy.transfer(interaction.user.id, user.id, nitters)
        except NitoError as e:
            await interaction.response.send_message(f"Couldn't: {e}", ephemeral=True)
            return
        await interaction.response.send_message(
            f"Sent {nitters} Nitter(s) to {user.display_name}.", ephemeral=True)

    @app_commands.command(description="Who has written the most.")
    async def leaderboard(self, interaction: discord.Interaction):
        rows = self.bot.economy.leaderboard(10)
        if not rows:
            await interaction.response.send_message("No one has earned yet.", ephemeral=True)
            return
        body = "\n".join(f"{i+1}. <@{u}> — {nito_str(b)}" for i, (u, b) in enumerate(rows))
        await interaction.response.send_message(body, ephemeral=True,
                                                allowed_mentions=discord.AllowedMentions.none())


async def setup(bot):
    await bot.add_cog(Wallet(bot))

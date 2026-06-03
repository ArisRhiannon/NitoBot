"""Admin cog — moderation with best practices: permission + role-hierarchy guards,
per-moderator rate limiting (anti-saturation), bulk caps, and audit reasons. Ephemeral
replies so the channel stays clean."""
import datetime

import discord
from discord import app_commands
from discord.ext import commands

from modutil import RateLimiter, can_moderate

PURGE_MAX = 100   # Discord bulk-delete ceiling; also a safety cap


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.limiter = RateLimiter(capacity=5, refill_per_sec=0.2)  # ~5 burst, 1 / 5s sustained

    async def _guard(self, interaction: discord.Interaction, target: discord.Member, perm: str) -> bool:
        if not self.limiter.allow((interaction.guild_id, interaction.user.id)):
            await interaction.response.send_message("slow down — too many actions at once.", ephemeral=True)
            return False
        me = interaction.guild.me
        ok, reason = can_moderate(
            interaction.user.top_role.position, target.top_role.position, me.top_role.position,
            actor_has_perm=getattr(interaction.user.guild_permissions, perm),
            target_is_self=target.id == interaction.user.id,
            target_is_owner=target.id == interaction.guild.owner_id)
        if not ok:
            await interaction.response.send_message(reason, ephemeral=True)
        return ok

    @app_commands.command(description="Kick a member.")
    @app_commands.guild_only()
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "—"):
        if not await self._guard(interaction, member, "kick_members"):
            return
        await member.kick(reason=f"{interaction.user}: {reason}"[:400])
        await interaction.response.send_message(f"kicked {member}.", ephemeral=True)

    @app_commands.command(description="Ban a member.")
    @app_commands.guild_only()
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "—"):
        if not await self._guard(interaction, member, "ban_members"):
            return
        await member.ban(reason=f"{interaction.user}: {reason}"[:400], delete_message_days=0)
        await interaction.response.send_message(f"banned {member}.", ephemeral=True)

    @app_commands.command(description="Time a member out (minutes).")
    @app_commands.guild_only()
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str = "—"):
        if not await self._guard(interaction, member, "moderate_members"):
            return
        minutes = max(1, min(minutes, 40320))  # Discord max 28 days
        until = discord.utils.utcnow() + datetime.timedelta(minutes=minutes)
        await member.timeout(until, reason=f"{interaction.user}: {reason}"[:400])
        await interaction.response.send_message(f"timed out {member} for {minutes} min.", ephemeral=True)

    @app_commands.command(description="Delete the last N messages here (max 100).")
    @app_commands.guild_only()
    async def purge(self, interaction: discord.Interaction, count: app_commands.Range[int, 1, PURGE_MAX]):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("you don't have permission for that.", ephemeral=True)
            return
        if not self.limiter.allow((interaction.guild_id, interaction.user.id)):
            await interaction.response.send_message("slow down — too many actions at once.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=count)
        await interaction.followup.send(f"deleted {len(deleted)} message(s).", ephemeral=True)

    @app_commands.command(description="Set channel slowmode (seconds, 0 to clear).")
    @app_commands.guild_only()
    async def slowmode(self, interaction: discord.Interaction, seconds: app_commands.Range[int, 0, 21600]):
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message("you don't have permission for that.", ephemeral=True)
            return
        await interaction.channel.edit(slowmode_delay=seconds)
        await interaction.response.send_message(f"slowmode set to {seconds}s.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Admin(bot))

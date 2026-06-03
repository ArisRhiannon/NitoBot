"""Voice cog — a bridge, kept deliberately light.

Joining/leaving voice works out of the box (needs PyNaCl). Turning speech into commands
is done by an EXTERNAL speech-to-text service that calls `handle_transcript(...)` — e.g.
a discord-ext-voice-recv + Whisper sidecar. We don't bundle audio capture/STT: it's heavy
and best run as its own service. Opt-in (add "voice" to modules)."""
import discord
from discord import app_commands
from discord.ext import commands

from voice_core import parse_voice_command


class Voice(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(description="Have Nito join your voice channel.")
    @app_commands.guild_only()
    async def join(self, interaction: discord.Interaction):
        voice = getattr(interaction.user, "voice", None)
        if not voice or not voice.channel:
            await interaction.response.send_message("join a voice channel first.", ephemeral=True)
            return
        await voice.channel.connect()
        await interaction.response.send_message("here.", ephemeral=True)

    @app_commands.command(description="Have Nito leave voice.")
    @app_commands.guild_only()
    async def leave(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc:
            await vc.disconnect(force=False)
        await interaction.response.send_message("leaving.", ephemeral=True)

    async def handle_transcript(self, guild: discord.Guild, member: discord.Member, text: str):
        """Called by an external STT service. Maps a wake-worded phrase to a safe action."""
        parsed = parse_voice_command(text)
        if not parsed:
            return None
        command, _ = parsed
        if command == "leave" and guild.voice_client:
            await guild.voice_client.disconnect(force=False)
            return "left voice"
        return None


async def setup(bot):
    await bot.add_cog(Voice(bot))

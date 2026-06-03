"""Social cog: gentle actions with counters. Nito's voice — quiet, no emojis."""
import discord
from discord import app_commands
from discord.ext import commands

from config import DATA
from social_store import SocialStore

ACTIONS = {"hug": "hugs", "pat": "pats", "kiss": "kisses"}


def _line(actor: str, verb: str, target: str, n: int) -> str:
    nth = {1: "the first time", 2: "the second time"}.get(n, f"{n} times now")
    return f"{actor} {verb} {target}. {nth}."


class ReturnView(discord.ui.View):
    def __init__(self, store: SocialStore, action: str, actor: discord.abc.User, target: discord.abc.User):
        super().__init__(timeout=120)
        self.store, self.action, self.actor, self.target = store, action, actor, target
        self.return_btn.label = f"return the {action}"

    @discord.ui.button(style=discord.ButtonStyle.secondary)
    async def return_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target.id:
            await interaction.response.send_message("that one isn't yours to return.", ephemeral=True)
            return
        n = self.store.record(self.action, self.target.id, self.actor.id)
        button.disabled = True
        await interaction.response.edit_message(
            content=_line(self.target.display_name, ACTIONS[self.action], self.actor.display_name, n), view=self)


class Social(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        DATA.mkdir(parents=True, exist_ok=True)
        self.store = SocialStore(str(DATA / "social.db"))

    async def _do(self, interaction: discord.Interaction, action: str, target: discord.User):
        if target.id == interaction.user.id:
            await interaction.response.send_message("you can keep that for someone else.", ephemeral=True)
            return
        if target.bot:
            await interaction.response.send_message("i appreciate it, but save it for a person.", ephemeral=True)
            return
        n = self.store.record(action, interaction.user.id, target.id)
        await interaction.response.send_message(
            _line(interaction.user.display_name, ACTIONS[action], target.display_name, n),
            view=ReturnView(self.store, action, interaction.user, target),
            allowed_mentions=discord.AllowedMentions.none())

    @app_commands.command(description="Give someone a hug.")
    async def hug(self, interaction: discord.Interaction, user: discord.User):
        await self._do(interaction, "hug", user)

    @app_commands.command(description="Give someone a pat.")
    async def pat(self, interaction: discord.Interaction, user: discord.User):
        await self._do(interaction, "pat", user)

    @app_commands.command(description="Give someone a kiss.")
    async def kiss(self, interaction: discord.Interaction, user: discord.User):
        await self._do(interaction, "kiss", user)

    @app_commands.command(description="How many gentle things you've received.")
    async def affection(self, interaction: discord.Interaction):
        u = interaction.user
        parts = [f"{a}: {self.store.received(u.id, a)}" for a in ACTIONS]
        await interaction.response.send_message("received — " + ", ".join(parts), ephemeral=True)


async def setup(bot):
    await bot.add_cog(Social(bot))

"""Automod cog — integrates goodfaith (trust-first, precision-biased).

Best practices baked in: starts in SHADOW (logs, never acts) so you can watch it
before enforcing; enforcement is reversible (delete + timeout, content stays in your
logs); goodfaith's core trust signal (msg_count / active_days) is fed from NitoBot's
own activity store. Flip a guild to ENFORCE only after `engine.readiness()` looks clean.
"""
import datetime
import time

import discord
from discord.ext import commands

from goodfaith import Engine, Mode, Policy
from goodfaith.extract import classify

from activity_store import ActivityStore
from automod_core import SAFE_HOSTS, account_age_days, make_message
from config import DATA


class AutoMod(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        DATA.mkdir(parents=True, exist_ok=True)
        self.activity = ActivityStore(str(DATA / "activity.db"))
        mode = Mode[bot.cfg.get("automod", {}).get("mode", "SHADOW").upper()]
        self.engine = Engine(Policy(mode=mode))
        self.timeout = datetime.timedelta(hours=1)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        self.activity.bump(message.guild.id, message.author.id, ts=time.time())
        decision = self.engine.evaluate(self._translate(message))
        if not decision.enforced:
            return  # SHADOW / allow: surface decision.explain() to an audit channel if you wish
        if decision.touches_message:
            try:
                await message.delete()
            except discord.HTTPException:
                pass
        if decision.punished and isinstance(message.author, discord.Member):
            try:
                await message.author.timeout(discord.utils.utcnow() + self.timeout,
                                             reason=decision.explain()[:400])
            except discord.HTTPException:
                pass

    def _translate(self, message: discord.Message) -> Message:
        member = message.author
        guild = message.guild
        own = (guild.vanity_url_code,) if getattr(guild, "vanity_url_code", None) else ()
        links = classify(message.content or "", own_invite_codes=own, safe_hosts=SAFE_HOSTS)
        server_age = 999.0
        if getattr(member, "joined_at", None):
            server_age = (discord.utils.utcnow() - member.joined_at).total_seconds() / 86400
        perms = getattr(member, "guild_permissions", None)
        is_staff = bool(perms and (perms.administrator or perms.ban_members
                                   or perms.kick_members or perms.manage_messages))
        return make_message(
            guild_id=guild.id, channel_id=message.channel.id, message_id=message.id,
            user_id=member.id, account_age_days=account_age_days(member.id), server_age_days=server_age,
            msg_count=self.activity.msg_count(guild.id, member.id),
            active_days=self.activity.active_days(guild.id, member.id),
            has_avatar=getattr(member, "avatar", None) is not None, is_staff=is_staff,
            content=message.content or "", mention_count=len(message.mentions or []),
            mentions_everyone=message.mention_everyone, has_attachments=bool(message.attachments),
            invite_urls=links.invite_urls, external_invite=links.external_invite,
            unsafe_links=links.unsafe_links, is_reply=message.reference is not None)


async def setup(bot):
    await bot.add_cog(AutoMod(bot))

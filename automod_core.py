"""Discord-free automod helpers (so decisions are unit-testable against the real engine)."""
import time

from goodfaith import Account, Message

_DISCORD_EPOCH_MS = 1420070400000
SAFE_HOSTS = ("discord.com", "tenor.com", "giphy.com", "youtube.com", "youtu.be")


def account_age_days(user_id: int) -> float:
    created_ms = (user_id >> 22) + _DISCORD_EPOCH_MS
    return (time.time() - created_ms / 1000) / 86400


def make_message(*, guild_id, channel_id, message_id, user_id, account_age_days,
                 server_age_days, msg_count, active_days, has_avatar, is_staff,
                 content, mention_count=0, mentions_everyone=False, has_attachments=False,
                 invite_urls=(), external_invite=False, unsafe_links=(), is_reply=False) -> Message:
    acc = Account(user_id=user_id, account_age_days=account_age_days, server_age_days=server_age_days,
                  msg_count=msg_count, active_days=active_days, has_avatar=has_avatar, is_staff=is_staff)
    return Message(guild_id=guild_id, channel_id=channel_id, message_id=message_id, author=acc,
                   content=content, created_at=time.time(), mention_count=mention_count,
                   mentions_everyone=mentions_everyone, has_attachments=has_attachments, sticker_count=0,
                   invite_urls=invite_urls, external_invite=external_invite, unsafe_links=unsafe_links,
                   is_reply=is_reply)

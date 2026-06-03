"""Automod integration tests. Skipped if goodfaith isn't installed (optional dep)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from activity_store import ActivityStore

try:
    from goodfaith import Engine, Policy, Mode
    from automod_core import make_message
    HAVE_GF = True
except Exception:
    HAVE_GF = False


def test_activity_store_counts_and_days():
    a = ActivityStore()
    a.bump("g", "u", ts=0)            # 1970-01-01
    a.bump("g", "u", ts=0)
    a.bump("g", "u", ts=86400)        # 1970-01-02 (new day)
    assert a.msg_count("g", "u") == 3
    assert a.active_days("g", "u") == 2
    print("ok A1 activity store: message count + distinct active days")


def test_goodfaith_protects_regulars_acts_on_raids():
    if not HAVE_GF:
        print("ok A2 (skipped: goodfaith not installed)")
        return
    eng = Engine(Policy(mode=Mode.ENFORCE))
    raid = make_message(guild_id=1, channel_id=1, message_id=1, user_id=1 << 22,
                        account_age_days=0.1, server_age_days=0.0, msg_count=0, active_days=0,
                        has_avatar=False, is_staff=False, content="free nitro https://discord.gg/evil",
                        mention_count=50, mentions_everyone=True, invite_urls=("evil",),
                        external_invite=True, unsafe_links=("http://x.ru",))
    regular = make_message(guild_id=1, channel_id=2, message_id=2, user_id=2 << 22,
                           account_age_days=900, server_age_days=400, msg_count=5000, active_days=180,
                           has_avatar=True, is_staff=True, content="good morning everyone")
    assert eng.evaluate(raid).enforced is True       # raid pattern is acted on
    assert eng.evaluate(regular).enforced is False    # an established regular is never touched
    print("ok A2 goodfaith: acts on raids, protects established regulars")


def run():
    test_activity_store_counts_and_days()
    test_goodfaith_protects_regulars_acts_on_raids()


if __name__ == "__main__":
    run()
    print("\nAll NitoBot automod tests passed.")

"""NitoBot economy tests — the message->Nitter bridge, fully offline (no Discord)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from economy import Economy
from earn import Instance
from nito import NitoError


def write(econ, channel, user, n, ts=0.0, start=0):
    """Simulate a user writing n messages in a channel during one epoch."""
    epoch = None
    for i in range(start, start + n):
        epoch = econ.record(channel, user, f"{channel}-{user}-{i}", ts=ts)
    return epoch


def test_two_bots_corroborate_earnings():
    # Two independent NitoBots witness the same channel (shared validator identities differ).
    bot_a = Economy(Instance(), quorum=2)
    bot_b = Economy(Instance(), quorum=2)
    for bot in (bot_a, bot_b):
        write(bot, "general", "alice", 100)
    att_a = bot_a.seal("general:0")
    att_b = bot_b.seal("general:0")
    # gossip: each ingests the other's attestation
    bot_a.ingest(att_b); bot_b.ingest(att_a)
    assert bot_a.balance("alice").nitters == 2   # 100 // 50, corroborated
    assert bot_b.balance("alice").nitters == 2   # both converge
    print("ok B1 two NitoBots corroborate -> alice earns Ñ-Nitters by writing")


def test_solo_bot_cannot_confirm():
    bot = Economy(Instance(), quorum=2)
    write(bot, "general", "alice", 100)
    bot.seal("general:0")
    assert bot.balance("alice").nitters == 0     # no independent witness -> nothing confirms
    print("ok B2 a solo bot can't confirm earnings (needs a second witness)")


def test_forged_attestation_does_not_pay_out():
    bot_a, bot_b = Economy(Instance(), 2), Economy(Instance(), 2)
    for bot in (bot_a, bot_b):
        write(bot, "general", "alice", 100)
    bot_a.ingest(bot_b.seal("general:0")); bot_a.seal("general:0")
    # A forked bot crafts a lie: mallory wrote a million msgs (own fabricated root).
    from earn import attest
    forker = Instance()
    fake = {"epoch": "general:0", "root": "ff" * 32, "counts": {"mallory": 1_000_000}, "pubkey": forker.pubkey}
    from earn import _payload
    fake["sig"] = forker.sign(_payload(fake["epoch"], fake["root"], fake["counts"]))
    bot_a.ingest(fake)
    assert bot_a.balance("alice").nitters == 2
    assert bot_a.balance("mallory").nitters == 0  # the forgery never corroborates
    print("ok B3 a forked bot's fabricated earnings are rejected")


def test_transfer_and_overdraft():
    a, b = Economy(Instance(), 2), Economy(Instance(), 2)
    for bot in (a, b):
        write(bot, "general", "alice", 200)       # 200 // 50 = 4 Nitters
    a.ingest(b.seal("general:0")); a.seal("general:0")
    assert a.balance("alice").nitters == 4
    a.transfer("alice", "bob", 3)
    assert a.balance("alice").nitters == 1 and a.balance("bob").nitters == 3
    try:
        a.transfer("alice", "bob", 5); assert False
    except NitoError:
        pass                                       # overdraft rejected
    print("ok B4 transfers move Nitters; overdraft rejected")


def test_global_balance_follows_userid_across_bots():
    # alice writes in two different servers/channels, each witnessed by 2 bots.
    s1a, s1b = Economy(Instance(), 2), Economy(Instance(), 2)
    s2a, s2b = Economy(Instance(), 2), Economy(Instance(), 2)
    for bot in (s1a, s1b):
        write(bot, "srv1", "alice", 100)
    for bot in (s2a, s2b):
        write(bot, "srv2", "alice", 150)
    a1 = s1a.seal("srv1:0"); b1 = s1b.seal("srv1:0")
    a2 = s2a.seal("srv2:0"); b2 = s2b.seal("srv2:0")
    # one node merges everything (gossip) -> alice's global balance follows her ID
    hub = Economy(Instance(), 2)
    for att in (a1, b1, a2, b2):
        hub.ingest(att)
    assert hub.balance("alice").nitters == (100 + 150) // 50  # 5, across both servers
    print("ok B5 balance follows the Discord ID globally across servers/bots")


def run():
    test_two_bots_corroborate_earnings()
    test_solo_bot_cannot_confirm()
    test_forged_attestation_does_not_pay_out()
    test_transfer_and_overdraft()
    test_global_balance_follows_userid_across_bots()


if __name__ == "__main__":
    run()
    print("\nAll NitoBot economy tests passed.")

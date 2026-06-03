"""Integration test for gossip P2P over real localhost HTTP."""
import sys, os, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from economy import Economy
from earn import Instance, attest, _payload
from peers import GossipServer, GossipClient


def _write(econ, n):
    for i in range(n):
        econ.record("general", "alice", f"m{i}", ts=0.0)
    return econ.seal("general:0")


async def _free_pair(secret=""):
    a, b = Economy(Instance(), 2), Economy(Instance(), 2)
    sa = GossipServer(a, port=8801, secret=secret)
    sb = GossipServer(b, port=8802, secret=secret)
    await sa.start(); await sb.start()
    return a, b, sa, sb


async def scenario_convergence():
    a, b, sa, sb = await _free_pair()
    att_a, att_b = _write(a, 100), _write(b, 100)   # both witness alice's 100 messages
    # cross-publish over HTTP
    await GossipClient(a, ["http://127.0.0.1:8802"]).publish(att_a)  # a -> b
    await GossipClient(b, ["http://127.0.0.1:8801"]).publish(att_b)  # b -> a
    assert a.balance("alice").nitters == 2, a.balance("alice").nitters
    assert b.balance("alice").nitters == 2
    await sa.stop(); await sb.stop()
    print("ok G1 two NitoBots converge over real HTTP gossip (alice = 2 Nitters)")


async def scenario_pull_sync():
    a, b, sa, sb = await _free_pair()
    _write(a, 150); _write(b, 150)
    await GossipClient(b, ["http://127.0.0.1:8801"]).pull()   # b pulls a's full ledger
    assert b.balance("alice").nitters == 3                    # 150 // 50, now corroborated on b
    await sa.stop(); await sb.stop()
    print("ok G2 a joining NitoBot pulls + corroborates the ledger")


async def scenario_secret_required():
    a, b, sa, sb = await _free_pair(secret="hunter2")
    att_a = _write(a, 100); _write(b, 100)
    # wrong/no secret -> rejected (no auth header)
    await GossipClient(a, ["http://127.0.0.1:8802"], secret="").publish(att_a)
    assert b.balance("alice").nitters == 0, "unauth gossip must be rejected"
    # correct secret -> accepted
    await GossipClient(a, ["http://127.0.0.1:8802"], secret="hunter2").publish(att_a)
    assert b.balance("alice").nitters == 2
    await sa.stop(); await sb.stop()
    print("ok G3 private federation: wrong network_secret is rejected, correct one accepted")


async def scenario_forged_over_wire():
    a, b, sa, sb = await _free_pair()
    att_a = _write(a, 100); _write(b, 100)
    await GossipClient(a, ["http://127.0.0.1:8802"]).publish(att_a)  # honest corroboration
    # forger POSTs a fabricated attestation directly
    forker = Instance()
    fake = {"epoch": "general:0", "root": "ff" * 32, "counts": {"mallory": 1_000_000}, "pubkey": forker.pubkey}
    fake["sig"] = "00" * 64   # invalid signature
    await GossipClient(b, ["http://127.0.0.1:8802"]).publish(fake)
    assert b.balance("alice").nitters == 2
    assert b.balance("mallory").nitters == 0, "forged attestation must be dropped on the wire"
    await sa.stop(); await sb.stop()
    print("ok G4 forged attestation is dropped at ingest (bad signature)")


def run():
    asyncio.run(scenario_convergence())
    asyncio.run(scenario_pull_sync())
    asyncio.run(scenario_secret_required())
    asyncio.run(scenario_forged_over_wire())


if __name__ == "__main__":
    run()
    print("\nAll NitoBot gossip integration tests passed.")

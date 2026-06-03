"""NitoBot economy — the bridge between Discord activity and NitoChain.

Pure Python, no Discord dependency, so it is fully unit-testable. Earnings come
ONLY from the corroborated earn protocol (earn.py): a user's confirmed balance is
what >= QUORUM independent NitoBots agreed they wrote. Transfers are layered on top.

Earning requires independent witnesses, so a channel needs >= QUORUM NitoBots
(the official one + community/forks) for messages there to confirm. This is the
honest consequence of forge-resistance: you earn where you are witnessed.
"""
import json
import time

from earn import Instance, EarnLedger, attest, MESSAGES_PER_NITTER  # noqa: F401
from nito import Nitos, NitoError

EPOCH_SECONDS = 600  # messages are committed in 10-minute windows per channel


def _tx_payload(tx: dict) -> bytes:
    return json.dumps({k: tx[k] for k in ("frm", "to", "nitters", "nonce")},
                      sort_keys=True, separators=(",", ":")).encode("utf-8")


class Economy:
    def __init__(self, instance: Instance = None, quorum: int = 2):
        self.instance = instance or Instance()
        self.ledger = EarnLedger(quorum=quorum)
        self._pending: dict = {}        # epoch -> set of (channel, author, message_id)
        self._transfers: list = []      # instance-signed transfer txs

    # ---- earning -----------------------------------------------------------
    def epoch_of(self, channel_id, ts: float = None) -> str:
        ts = time.time() if ts is None else ts
        return f"{channel_id}:{int(ts) // EPOCH_SECONDS}"

    def record(self, channel_id, author_id, message_id, ts: float = None) -> str:
        epoch = self.epoch_of(channel_id, ts)
        self._pending.setdefault(epoch, set()).add((str(channel_id), str(author_id), str(message_id)))
        return epoch

    def seal(self, epoch: str) -> dict:
        """Commit + sign this instance's view of an epoch (then gossip to peers)."""
        leaves = self._pending.get(epoch)
        if not leaves:
            return None
        att = attest(self.instance, epoch, leaves)
        self.ledger.add(att)
        return att

    def ingest(self, att: dict) -> None:
        """Receive a peer NitoBot's attestation (a forged one simply won't corroborate)."""
        self.ledger.add(att)

    def earned(self, user) -> int:
        return self.ledger.balance(str(user)).nitters

    # ---- transfers (instance-authorized; see honest caveat in README) ------
    def _net_transfer(self, user) -> int:
        u, net = str(user), 0
        for t in self._transfers:
            if t["to"] == u:
                net += t["nitters"]
            if t["frm"] == u:
                net -= t["nitters"]
        return net

    def balance(self, user) -> Nitos:
        return Nitos(self.earned(user) + self._net_transfer(user))

    def transfer(self, frm, to, amount) -> dict:
        amt = amount.nitters if isinstance(amount, Nitos) else int(amount)
        if amt <= 0:
            raise NitoError("transfer amount must be positive.")
        if str(frm) == str(to):
            raise NitoError("can't transfer to yourself.")
        if self.balance(frm).nitters < amt:
            raise NitoError("insufficient Nito.")
        tx = {"frm": str(frm), "to": str(to), "nitters": amt, "nonce": len(self._transfers)}
        tx["sig"] = self.instance.sign(_tx_payload(tx))
        self._transfers.append(tx)
        return tx

    def leaderboard(self, n: int = 10):
        users = set(self.ledger.balances())
        for t in self._transfers:
            users.add(t["to"]); users.add(t["frm"])
        ranked = sorted(((u, self.balance(u)) for u in users), key=lambda x: -x[1].nitters)
        return [(u, b) for u, b in ranked if b.nitters > 0][:n]

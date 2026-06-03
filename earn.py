"""NitoChain v0.2 — the earn protocol: the ONLY way Nito is minted.

How forgery is actually resisted (honest design)
-------------------------------------------------
A NitoBot cannot *prove in software* that it is unforked — an operator controls
its machine, and any embedded key in an "encrypted logger" is extractable at
runtime (the white-box problem is unsolved). So we do NOT root trust in a binary.

Instead trust is rooted in **reproduction + corroboration**:

1. The logger is DETERMINISTIC. For an `epoch` (a channel + time window) it commits
   to exactly what it observed — the set of `(channel, author, message_id)` leaves —
   as a single `log_root = sha256(sorted unique leaves)`. Two honest NitoBots in the
   same channel see the same messages and therefore compute the SAME root and the
   SAME per-author counts.
2. Each instance signs `{epoch, log_root, counts}` with its ed25519 key.
3. An epoch's counts are FINALIZED (and only then minted) when **>= QUORUM distinct
   instances independently agree on the same (root, counts)**. A forked logger that
   fabricates messages produces a different root/counts → it lands in its own group,
   never reaches quorum, and is rejected. A lone instance (no independent witness)
   never finalizes — *you earn where there are independent witnesses*.
4. If an epoch has two conflicting groups that both reach quorum, it is treated as
   CONTESTED and mints nothing (deterministic, so all nodes agree).

The attestation set is a CRDT (grow-only set keyed by (pubkey, epoch)); balances are
a pure, order-independent fold over it, so independent NitoBots converge by gossiping
and merging — no central server.

Honest limits (not hidden): a single operator running >= QUORUM colluding instances
with real sybil accounts in a private channel can still self-corroborate. That is the
Sybil/collusion ceiling; pure software cannot close it. It is bounded by Discord's own
rate limits + the goodfaith automod, is auditable, and is meant to be raised later with
validator staking/slashing or proof-of-personhood (documented as future, not claimed now).
"""
import hashlib
import json
from collections import Counter, defaultdict
from typing import Dict, Iterable, List, Tuple

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization

from nito import Nitos, NitoError

MESSAGES_PER_NITTER = 50          # protocol-fixed mint rule: writing is the only source
QUORUM = 2                        # independent instances that must agree to finalize


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def log_root(records: Iterable[Tuple[str, str, str]]) -> str:
    """Deterministic commitment to observed (channel, author, message_id) leaves."""
    leaves = sorted({f"{c}|{a}|{m}" for (c, a, m) in records})
    return _sha("\n".join(leaves))


def _payload(epoch: str, root: str, counts: Dict[str, int]) -> bytes:
    return json.dumps({"epoch": epoch, "root": root, "counts": dict(sorted(counts.items()))},
                      sort_keys=True, separators=(",", ":")).encode("utf-8")


class Instance:
    """A NitoBot's validator identity (ed25519). Genuine and forked instances are
    indistinguishable by key alone — which is exactly why trust comes from agreement."""
    def __init__(self, secret: bytes = None):
        self._sk = Ed25519PrivateKey.from_private_bytes(secret) if secret else Ed25519PrivateKey.generate()
        self.pubkey = self._sk.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()

    def secret(self) -> bytes:
        return self._sk.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                      serialization.NoEncryption())

    def sign(self, data: bytes) -> str:
        return self._sk.sign(data).hex()

    @staticmethod
    def verify(pubkey_hex: str, data: bytes, sig_hex: str) -> bool:
        try:
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(pubkey_hex)).verify(bytes.fromhex(sig_hex), data)
            return True
        except Exception:
            return False


def attest(instance: Instance, epoch: str, records: Iterable[Tuple[str, str, str]]) -> dict:
    """An instance commits to (and signs) what it observed in an epoch."""
    recs = set(records)                                  # a message_id counts once
    counts = dict(Counter(a for (_, a, _) in recs))
    root = log_root(recs)
    return {"epoch": epoch, "root": root, "counts": counts,
            "pubkey": instance.pubkey, "sig": instance.sign(_payload(epoch, root, counts))}


class EarnLedger:
    """Grow-only, CRDT set of attestations. Balances are a pure fold over it."""
    def __init__(self, quorum: int = QUORUM):
        self.quorum = quorum
        self.atts: Dict[Tuple[str, str], dict] = {}     # (pubkey, epoch) -> attestation

    def add(self, att: dict) -> "EarnLedger":
        if not Instance.verify(att["pubkey"], _payload(att["epoch"], att["root"], att["counts"]), att["sig"]):
            raise NitoError("rejected: invalid attestation signature.")
        self.atts[(att["pubkey"], att["epoch"])] = att   # idempotent
        return self

    def merge(self, other: "EarnLedger") -> "EarnLedger":
        for att in other.atts.values():
            self.add(att)
        return self

    def _finalized_messages(self) -> Dict[str, int]:
        # epoch -> {(root, counts_fingerprint): (set_of_pubkeys, counts)}
        epochs: Dict[str, Dict[tuple, list]] = defaultdict(dict)
        for (pub, epoch), att in self.atts.items():
            fp = json.dumps(dict(sorted(att["counts"].items())), sort_keys=True)
            grp = epochs[epoch].setdefault((att["root"], fp), [set(), att["counts"]])
            grp[0].add(pub)
        totals: Dict[str, int] = defaultdict(int)
        for epoch, groups in epochs.items():
            winners = [counts for (pubs, counts) in groups.values() if len(pubs) >= self.quorum]
            if len(winners) == 1:                        # exactly one corroborated truth → finalize
                for user, n in winners[0].items():
                    totals[user] += n
            # 0 winners (no quorum) or >1 (contested) → mint nothing for this epoch
        return totals

    def balances(self) -> Dict[str, Nitos]:
        return {u: Nitos(n // MESSAGES_PER_NITTER) for u, n in self._finalized_messages().items()}

    def balance(self, user: str) -> Nitos:
        return Nitos(self._finalized_messages().get(user, 0) // MESSAGES_PER_NITTER)

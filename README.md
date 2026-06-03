# NitoBot

<p align="left">
  <img src="https://img.shields.io/badge/Version-0.1.0-blueviolet?style=flat-square" alt="Version">
  <img src="https://img.shields.io/badge/License-MIT-blue?style=flat-square" alt="License">
  <img src="https://img.shields.io/badge/Python-3.10%2B-brightgreen?style=flat-square" alt="Python">
  <img src="https://img.shields.io/badge/discord.py-2.x-5865F2?style=flat-square" alt="discord.py">
</p>

**A small, modular Discord bot whose economy is the [NitoChain](https://github.com/ArisRhiannon/NitoChain):
the only way to earn Nito is to write, and earnings follow your Discord ID across every
server and fork — with no central server.** Nito herself is quiet and polite (see
[`persona.md`](persona.md)) — no emojis, no cringe.

## Install (Windows & Linux/macOS)

```bash
python3 install.py        # Linux/macOS  (or: ./install.sh)
py install.py             # Windows      (or: ./install.ps1)
```

It creates a venv, installs deps, writes `data/config.json`, generates this bot's
validator identity, and asks for your Discord token. Then:

```bash
.venv/bin/python bot.py   # NITOBOT_TOKEN in .env or env
```

## How earning works (and why a fork can't cheat)

Earning is **NitoChain's earn protocol** ([`earn.py`](earn.py)): minting is part of the
protocol, so no operator — not even a fork — can change the rule.

- **50 messages you write = 1 Nitter** (1 Nito = 100 Nitters).
- Each bot commits to what it observed per epoch as a deterministic `log_root`, signs it
  (ed25519), and gossips it to peer bots.
- Earnings **confirm only when ≥ QUORUM independent NitoBots agree** on the same commitment.
  A fork that fabricates messages produces a different commitment → it never corroborates →
  it's rejected. Your **NitoWallet** is keyed to your absolute Discord user ID, so a node
  that merges the gossiped, signed ledger shows the same balance for you everywhere.

> **Honest limits (we don't pretend otherwise).** Pure software can't make a logger
> tamper-proof — encryption is a deterrent, corroboration is the real guarantee. A single
> operator running ≥ QUORUM colluding bots with real sybil accounts in a private channel can
> still self-corroborate; that ceiling needs validator staking or proof-of-personhood
> (future). And: **a channel needs ≥ QUORUM independent NitoBots present for messages there
> to confirm** — you earn where you are witnessed. Transfers are instance-authorized for now.
> Full details in the [NitoChain README](https://github.com/ArisRhiannon/NitoChain).

## Modules (cogs)

Enable/disable in `data/config.json` → `modules`.

| Cog | Commands | Status |
| --- | --- | --- |
| `meta` | `/ping` | ✓ |
| `earn` | (passive: counts messages, seals & gossips epochs) | ✓ |
| `wallet` | `/balance` `/pay` `/leaderboard` | ✓ |
| `social` | `/hug` `/pat` `/kiss` + counters | planned |
| `admin` | moderation, best-practice rate limits | planned |
| `automod` | integrates [goodfaith](https://github.com/ArisRhiannon/goodfaith) | planned |
| `llm` | OpenAI-compatible chat (persona + memory) | planned |
| `voice` | voice-command bridge | planned |

Adding a cog: drop `cogs/yourcog.py` with a `setup(bot)`, add its name to `modules`.

## Federation (no central server)

NitoBots sync the earn ledger by gossip. Each bot runs a small endpoint
(`POST /gossip`, `GET /ledger`) and lists peers in `data/config.json`:

```json
"peers": ["https://nito.example.com"],
"network_secret": "shared-phrase",   // same on your bots = private federation
"gossip_host": "127.0.0.1", "gossip_port": 8787
```

Security, by default:
- Every attestation is **ed25519-signed and self-validating** — a forged one is dropped on
  arrival, so the endpoint can be open without risking fake payouts.
- A **`network_secret`** (same on all your bots) requires an HMAC on every request — a
  private, authenticated federation.
- The endpoint **binds `127.0.0.1`** by default. To federate across the internet, expose it
  over **TLS** via a reverse proxy or a Cloudflare tunnel (`cloudflared tunnel ... ->
  http://localhost:8787`); user activity then travels encrypted between bots.

> Privacy note: attestations carry Discord IDs + per-epoch message counts. Use TLS + a
> private `network_secret` if you don't want to share that. Discord IDs are enumerable, so
> hashing wouldn't give strong anonymity — we don't pretend it would.

## Tested

```bash
python3 tests/test_economy.py   # message->Nitter economy, offline (5/5)
python3 tests/test_gossip.py    # P2P gossip over real HTTP: convergence, auth, forgery (4/4)
```

Both run without Discord. Live Discord behavior needs a bot token.

## Roadmap

v0.1 (this): core + installer + `meta`/`earn`/`wallet` + **federated gossip (secure by
default)** + tested economy & P2P. Next: `social`, `admin`, `automod` (goodfaith),
`llm` (+ persona + holographic memory), `voice`.

## License

MIT — © 2026 ArisRhiannon

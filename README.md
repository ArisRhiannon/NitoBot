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
[`persona.md`](persona.md)) 

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

## As a terminal CLI

NitoBot is also a pip-installable package with a `nitobot` command:

```bash
pipx install git+https://github.com/ArisRhiannon/NitoBot     # or: pip install -e .
nitobot setup     # creates data/config.json, persona.md, asks for your token
nitobot run       # start the bot
nitobot update    # pull the latest code (see below)
nitobot version
nitobot persona status            # inspect the adaptive style layer (HoloPersona)
nitobot persona explain --user <id>
```

## Updating — `nitobot update`

`nitobot update` fast-forwards the code from git. **It never touches your settings**: your
`persona.md` (Nito's soul), everything in `data/` (config, wallet key, memory) and `.env`
are gitignored, so an update only changes code. The tracked template is `persona.default.md`;
your `persona.md` is created from it once and then left alone. If you've edited tracked files
or the branch diverged, the update refuses to clobber them and tells you to resolve it in git.

## Reading the conversation

When Nito replies, she reads the channel's recent history — up to `history_limit` messages
(default **300**, set in `data/config.json`) — and includes it as context, **including
messages from bots and from herself**, so she follows the actual conversation rather than
just the line that pinged her.

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
| `social` | `/hug` `/pat` `/kiss` `/affection` + counters | ✓ |
| `admin` | `/kick` `/ban` `/timeout` `/purge` `/slowmode`; guards + rate limits | ✓ |
| `automod` | integrates [goodfaith](https://github.com/ArisRhiannon/goodfaith); starts in SHADOW | ✓ (opt-in) |
| `llm` | **agentic** `/ask` + replies on mention; OpenAI-compatible tool-calling, persona + holographic memory | ✓ (opt-in) |
| `voice` | `/join` `/leave` + transcript bridge (STT is external) | ✓ (opt-in) |

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
python3 tests/test_social.py    # social action counters (3/3)
python3 tests/test_automod.py   # activity store + goodfaith decisions (2/2; needs goodfaith)
python3 tests/test_llm.py       # memory recall + OpenAI-compatible client via mock server (3/3)
python3 tests/test_admin_voice.py  # rate limiter + moderation guard + voice parser (3/3)
python3 tests/test_holo.py      # holographic HDC memory: portable, multilingual, cheap (6/6)
python3 tests/test_agent.py     # agent tool-calling loop + admin guardrails (3/3)
python3 tests/test_native.py    # C reference reproduces identical vectors (conformance)
python3 tests/test_holopersona.py  # bounded adaptive personality: trace/immunity/learning/drift (8/8)
```

## Agentic (OpenAI-compatible tool calling)

The `llm` cog isn't just chat — Nito is an **agent**. Through standard OpenAI-compatible
function calling she can decide to use tools, run them, and answer with the results:

- **Conversation tools (anyone):** `get_balance`, `leaderboard`, `recall_memory`.
- **Admin tools (admins only):** `timeout_member`, `purge_messages`, `set_slowmode`.

So an admin can say *“Nito, mute that spammer for 10 minutes”* and she'll call
`timeout_member` — but the model only **proposes**; the code **authorizes**. Every admin
tool is gated twice: in `agent.dispatch` (caller must be admin) and again by Discord
permission + role-hierarchy guards in the handler. The LLM can never escalate privilege,
and Nito never claims to have acted unless a tool actually confirmed it. Works with any
OpenAI-compatible endpoint (OpenAI, Ollama, llama.cpp, LM Studio). See `agent.py`.

```text
model -> tool_calls -> dispatch (guarded) -> tool results -> final reply   (max 4 steps)
```

## HoloPersona — bounded adaptive personality

> **Stable at the core. Adaptive at the edges.**

HoloPersona is NitoBot's bounded adaptive personality layer. It stores replayable evidence
from interactions and consolidates **stable** patterns into style preferences, while preserving
an **immutable core persona** from `persona.md`. It is not a soul and does not "truly understand"
anyone — it's a small, auditable system for learning conversational *style*.

Four separate layers (the plan's thesis):

| Layer | Question | Speed |
|---|---|---|
| **Core persona** (`persona.md`) | who Nito *is* | never changes automatically |
| **HoloPersona** | *how* Nito should respond | slow, consolidated |
| **HoloMood** | this conversation's tilt | fast, decays ~0.85 / 10 min |
| HoloMemory | what Nito knows | (the HDC memory above) |

How it works, and why it's safe:

- **The model proposes, the deterministic engine decides.** Every reply can carry a compact
  `holo_trace`, but it's weak evidence (weight 0.25). Trusted signals are the cheap, LLM-free
  ones extracted from your own words (e.g. "sin emojis", "más corto", "explica más" — weight 0.70).
- **Evidence-weighted beliefs.** A trait's learning rate shrinks as evidence accumulates
  (`lr = base·confidence·reward / √(1+evidence)`), so one message can't overwrite a personality,
  but a repeated, explicit preference does consolidate.
- **Identity bounds.** Every learned style is *projected into* hard bounds (e.g. `emoji ≤ 0.10`),
  so adaptation can never push Nito out of character. `persona.md` is never rewritten.
- **HoloImmunity.** Prompt injection, abuse, secrets and "rewrite your persona" attempts are
  detected and learned with weight **0**. Silence is neutral, never punishment.
- **Replayable + auditable.** Everything lives in a `holo_events` ledger; `current_persona =
  replay(events)`. Inspect, freeze, reset or export it from the CLI:

```bash
nitobot persona status
nitobot persona explain --user <id>     # per-user learned style + confidence
nitobot persona drift   --user <id>     # how far from core, flags traits over the cap
nitobot persona freeze                  # pin style to the core persona
nitobot persona reset   --user <id>     # wipe a user's learned style
nitobot persona export                  # dump the event ledger
```

**Status (honest):** implemented and tested offline are the trace parser/validator, HoloImmunity,
deterministic signals, evidence-weighted per-user learning, session mood, identity bounds, the
replayable ledger and the CLI (`tests/test_holopersona.py`, 8/8). **Not done yet:** F3 periodic
consolidation/clustering and *enforcing* the drift cap (it's currently reported, not capped),
F4 full HDC event-vector binding, and wiring HoloPersona into the live LLM cog (style-card
injection + event recording). It runs in **shadow mode** — it does not yet change live replies.

## Holographic memory

The `llm` cog's memory is a real **hyperdimensional-computing (HDC/VSA)** store, not a
keyword index: text → one 8192-bit hypervector via byte-n-gram bind/bundle, recall by
Hamming distance. It is language-agnostic (any UTF-8), robust to typos/morphology, and
bitwise (no model/GPU, ~1 KB/memory). Cost is O(len·DIM): ≈2.6 ms to encode and a
vectorized ≈55 ms to scan 10k memories. The encoding is a fixed cross-language spec
([`HOLO_SPEC.md`](HOLO_SPEC.md)); `native/holo.c` is an independent, numpy-free C
implementation that reproduces **byte-identical** vectors (verified in `tests/test_native.py`)
— so the memory is portable to other languages and microcontrollers. `remember/recall` is
the drop-in point for a different backend.

All run without Discord. Live Discord behavior needs a bot token.

## Roadmap

All planned cogs are in: `meta` · `earn` · `wallet` · `social` · `admin`, plus opt-in
`automod` (goodfaith), `llm` (OpenAI-compatible + persona + memory), and `voice`, over a
**secure federated gossip** layer. Next: gossip peer auto-discovery, richer LLM memory
backends, and bundled voice STT — all on top of the tested cores here.

## License

MIT — © 2026 ArisRhiannon

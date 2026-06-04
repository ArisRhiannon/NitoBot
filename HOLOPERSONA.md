# HoloPersona

> **Stable at the core. Adaptive at the edges.**

HoloPersona is NitoBot's **bounded, replayable, auditable** adaptive personality layer. It learns
*how* Nito should respond to each person from real interactions, while the core persona from
`persona.md` stays **immutable**. It is not a soul and does not "understand" anyone — it's a small,
deterministic system for learning conversational **style**, designed so it can never drift out of
character, be manipulated, or become a black box.

This document describes what is actually implemented (see `holopersona/`), with an honest scope
section at the end. Tests: `tests/test_holopersona.py` (12) + `tests/test_trace_mode.py` (2).

---

## Thesis — four separate layers

| Layer | Answers | Where | Speed |
|---|---|---|---|
| **Core persona** | who Nito *is* | `persona.md` → `NITO_CORE` | never changes automatically |
| **HoloPersona** | *how* she should respond | `genome.py` + ledger replay | slow, consolidated |
| **HoloMood** | this conversation's tilt | `mood.py` (RAM) | fast, decays ~0.85 / 10 min |
| HoloMemory | what she knows | `memory.py` (HDC) | recall on demand |

> HoloMemory remembers what happened. HoloPersona remembers how to be.

## Design principles

- **The model proposes, the deterministic engine decides.** The LLM's self-report (`holo_trace`)
  is *weak* evidence (weight 0.25). The trusted evidence is the cheap, LLM-free signals pulled from
  the user's own words (weight 0.70).
- **Consolidation, not reflexes.** A single message never rewrites personality; learning rate
  shrinks as evidence accumulates, so only repeated, consistent preferences consolidate.
- **`persona.md` is immutable.** HoloPersona only produces a *style card* to guide the LLM and
  records evidence to a ledger. It never writes the persona file.
- **Everything is replayable.** `current_persona = replay(holo_events)` — auditable, reversible,
  exportable, resettable.

```
message → deterministic signals + (optional) holo_trace → holo_events ledger
        → replay → per-user StyleGenome → project to identity bounds + drift cap → style card
```

---

## Components

### 1. Core persona & identity bounds — `bounds.py`
A 12-trait continuous **style genome**: `depth, brevity, warmth, directness, playfulness,
structure, skepticism, softness, ornamentation, initiative, caution, emoji`. `NITO_CORE` is Nito's
baseline tendency (low emoji/ornamentation, medium warmth, honest). `project()` clamps any candidate
style into hard **identity bounds** (`emoji ≤ 0.10`, ornamentation/playfulness/directness ranges,
warmth floor). Learning can only ever move *within* these bounds.

### 2. Drift cap — `controller.py`
On top of the bounds, every learned trait is clamped to within **±0.35 of the core** before it can
influence a reply (`HoloPersona._cap`). This is **enforced**, not just reported: `relationship_means`
returns capped values; `drift()` separately reports the *raw* belief delta and flags `OVER CAP`.

### 3. Deterministic signals — `signals.py`
LLM-free phrases (Spanish + English) map to trait nudges, e.g. `"sin emojis" → emoji −`,
`"más corto" → brevity +`, `"explica más" → depth +`, `"cringe" → ornamentation −`. Evidence weights:

```
explicit feedback 1.00 · moderation 1.00 · deterministic text 0.70 · behavior 0.30 · holo_trace 0.25 · silence 0.00
```

Silence is **neutral**, never punishment.

### 4. HoloTrace & trace mode — `trace.py`, `respond.py`
`parse_response(raw)` splits the LLM output into `(reply, trace)`; bad JSON never blocks the visible
reply. `validate_trace` clamps every field to its legal range (`next_nudge ∈ [-1,1]`, others
`[0,1]`), drops unknown traits, and immunity-scrubs `memory_candidates`. **Trace mode** (`respond.py`,
opt-in `holopersona.trace`) makes the *same* LLM call return `{reply, holo_trace}` — no extra
classifier call, exactly as the plan requires.

### 5. Learning — `genome.py`
`TraitBelief(mean, evidence, volatility, last_updated)`; the update rule:

```
lr = base_lr · confidence · reward_weight / sqrt(1 + evidence)
mean = clamp(mean + lr · nudge, 0, 1);  evidence += confidence · reward_weight
```

Beliefs are seeded at the **core prior**, so learning moves a trait *away from the core*, not toward
a neutral 0.5. `StyleGenome.evidenced_means()` returns only traits with real accumulated evidence.

### 6. Session mood — `mood.py`
A per-conversation tilt that decays `0.85` every 10 minutes and lives only in RAM — a heated thread
can never become permanent personality.

### 7. Active style card — `card.py`
Blends `core + relationship + (server) + mood`, projects into bounds, and renders compact guidance
that is injected into the LLM prompt. Each trait renders independently, so a learned preference
actually changes the card.

### 8. Event ledger & replay — `ledger.py`
SQLite `holo_events` stores, per turn: timestamps, scope ids, **hashes** of input/reply (not the
raw text), the (optional) `holo_trace`, the deterministic signals, the outcome, and a non-reversible
HDC `event_vec`. `replay_user(ledger, user_id, core)` deterministically rebuilds the StyleGenome.
`holo_snapshots` stores consolidation snapshots.

### 9. HDC event layer — `holo_hdc.py`
Each event is one holographic hypervector built by **role-filler binding**
(`user_text, bot_tone, intent, outcome, context, time`), bundled by majority vote. Reuses the
memory's cross-implementation `HOLO_SPEC` substrate (DIM = 8192, `encode_bits`, fixed seed), so
vectors are deterministic and reproducible. XOR binding is self-inverse; `similarity` is Hamming;
`consistency()` is the mean pairwise similarity of a user's events (how recurring they are). The
event vector is **non-reversible** — the raw text cannot be recovered from it.

### 10. Consolidation & snapshots — `controller.consolidate()`
Periodic pass that promotes stable, well-evidenced, capped shifts into an auditable `holo_snapshots`
row and returns a report `{user: {promoted: [(trait, Δ)], consistency: x}}`.

### 11. HoloImmunity — `immunity.py`
Deterministic refusal to **learn** prompt injection, abuse, secrets, or "rewrite your persona"
attempts (learned with weight 0). `safe_to_learn`, `scrub_candidates`. This is safety, applied both
in `validate_trace` and before any consolidation.

---

## CLI

```bash
nitobot persona status                 # events, users, snapshots, frozen, drift cap
nitobot persona explain --user <id>    # per-user learned style + confidence
nitobot persona drift   --user <id>    # raw deltas vs core, flags traits over the cap
nitobot persona consolidate            # promote stable shifts, write a snapshot (+ HDC consistency)
nitobot persona freeze | unfreeze      # pin style to / release from the core
nitobot persona reset   --user <id>    # wipe a user's learned style
nitobot persona export                 # dump the event ledger
```

## Integration & config

The `llm` cog builds a per-user, drift-capped style card and injects it into the prompt, then
records each turn as bounded evidence. Config (`data/config.json`):

```json
"holopersona": { "enabled": true, "trace": false }
```

`enabled` (default on with the LLM) toggles the whole layer; `trace` switches the response path to
single-call trace mode. Any HoloPersona error is swallowed so it can never break a reply, and
`persona.md` is never modified.

---

## Status — honest

**Implemented & tested offline:** trace parser/validator, HoloImmunity, deterministic signals,
evidence-weighted per-user (relationship) learning, session mood, identity bounds + enforced drift
cap, periodic consolidation with snapshots, the HDC event-vector layer + consistency metric,
single-call trace mode, the replayable ledger, the CLI, and the (compile-checked) cog wiring.

**Not done yet:**
- Only the **session** and **per-user relationship** layers learn — *server-wide* and *global*
  style layers are not implemented.
- **Follow-up outcome shaping** (`observe_followup`): outcomes are recorded but not yet inferred
  from the next message.
- **HDC-clustering-driven promotion**: consistency is *reported*, but deterministic signals still
  drive promotion.
- Live behaviour is verified via unit/mock tests; the Discord cog itself is compile-checked only
  (discord.py is not installed in CI here).

## Claim for the README (honest)

> HoloPersona is NitoBot's bounded adaptive personality layer. It stores replayable holographic
> evidence from interactions and periodically consolidates stable patterns into style preferences,
> while preserving an immutable core persona from `persona.md`.

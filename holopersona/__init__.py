"""HoloPersona v3 — NitoBot's bounded, replayable, auditable adaptive personality layer.

It stores replayable holographic evidence from interactions and consolidates stable
patterns into style preferences, while preserving an immutable core persona from persona.md.
Stable at the core, adaptive at the edges.

Status: F0-F2 core + HoloImmunity (safety), shadow-mode. F3 (periodic consolidation /
clustering), F4 (full HDC event-vector binding) and live cog wiring are later phases."""
from .bounds import TRAITS, DEFAULT_BOUNDS, NITO_CORE, project
from .controller import HoloPersona
from .genome import StyleGenome, TraitBelief, update_trait
from .ledger import Ledger, replay_user
from .mood import SessionMood
from .trace import parse_response, validate_trace
from . import immunity, signals, card

__all__ = [
    "HoloPersona", "StyleGenome", "TraitBelief", "update_trait", "Ledger", "replay_user",
    "SessionMood", "parse_response", "validate_trace", "project", "TRAITS",
    "DEFAULT_BOUNDS", "NITO_CORE", "immunity", "signals", "card",
]

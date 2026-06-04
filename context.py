"""Build a compact chat transcript for the agent's context (Discord-free, testable).

Reads recent messages (humans AND bots — including Nito herself and other bots), keeps the
NEWEST that fit a character budget, and renders one `name: content` line each so the model
has real conversational context without blowing the prompt."""
from typing import List, Tuple


def build_transcript(messages: List[Tuple[str, str, bool]], char_budget: int = 6000) -> str:
    """messages: oldest->newest list of (display_name, content, is_bot). Returns a transcript
    string trimmed from the oldest end to fit char_budget; newest is always kept."""
    lines = []
    for name, content, is_bot in messages:
        content = " ".join((content or "").split())          # collapse whitespace/newlines
        if not content:
            continue
        tag = " [bot]" if is_bot else ""
        lines.append(f"{name}{tag}: {content}")
    kept, total = [], 0
    for line in reversed(lines):                              # keep newest first, then re-order
        if total + len(line) + 1 > char_budget:
            break
        kept.append(line)
        total += len(line) + 1
    return "\n".join(reversed(kept))

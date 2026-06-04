"""Active style card — fuse core + relationship + server + session mood, project into the
identity bounds, and render compact guidance for the LLM. The core always dominates;
the other layers only nudge, and the bounds clamp the result."""
from .bounds import TRAITS, project

# How far each layer may pull the final style. Core dominates by construction.
W_REL, W_SERVER, W_MOOD = 0.50, 0.30, 0.25


def blend(core, relationship=None, server=None, mood=None, bounds=None):
    rel, srv, mo = relationship or {}, server or {}, mood or {}
    out = {}
    for t in TRAITS:
        base = core.get(t, 0.5)
        out[t] = (base
                  + W_REL * (rel.get(t, base) - base)
                  + W_SERVER * (srv.get(t, base) - base)
                  + W_MOOD * mo.get(t, 0.0))
    return project(out, bounds)


def render(g) -> str:
    def hi(t):
        return g[t] >= 0.60

    def lo(t):
        return g[t] <= 0.25

    lines = ["Current style guidance:"]
    lines.append("- Be direct and technically honest." if hi("directness")
                 else "- Be gentle and measured.")
    lines.append("- Prefer depth and explicit reasoning." if hi("depth")
                 else "- Keep it concise." if hi("brevity")
                 else "- Match the detail the question needs.")
    if lo("emoji"):
        lines.append("- Avoid emojis.")
    if lo("ornamentation"):
        lines.append("- Avoid exaggerated cuteness; restraint over theatrics.")
    if hi("structure"):
        lines.append("- Use clear structure.")
    if hi("warmth"):
        lines.append("- Keep a warm, supportive tone.")
    if hi("softness"):
        lines.append("- Soft, not childish.")
    return "\n".join(lines)


def style_card(core, relationship=None, server=None, mood=None, bounds=None) -> str:
    return render(blend(core, relationship, server, mood, bounds))

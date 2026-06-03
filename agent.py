"""NitoBot agent — OpenAI-compatible tool/function calling for conversation + admin.

The model PROPOSES tool calls; this code AUTHORIZES and executes them. Admin tools are
gated on `ctx.is_admin` here (defense in depth) and again by Discord permission/hierarchy
guards in the cog's handlers — the LLM can never escalate privilege. Conversation tools
(balance, leaderboard, memory) are safe for anyone. Discord-free so it's fully testable.
"""
import json
from typing import Awaitable, Callable, Dict, List

ADMIN_TOOLS = {"timeout_member", "purge_messages", "set_slowmode"}


def _fn(name, desc, props, required):
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object", "properties": props, "required": required}}}


def tool_schemas() -> List[dict]:
    s = {"type": "string"}
    i = {"type": "integer"}
    return [
        _fn("get_balance", "Get a member's NitoWallet balance in Nito.", {"user_id": s}, ["user_id"]),
        _fn("leaderboard", "List the top Nito earners in this server.", {}, []),
        _fn("recall_memory", "Recall relevant things Nito remembers about this context.", {"query": s}, ["query"]),
        _fn("timeout_member", "[admin] Time a member out for N minutes.",
            {"user_id": s, "minutes": i, "reason": s}, ["user_id", "minutes"]),
        _fn("purge_messages", "[admin] Delete the last N messages in this channel (max 100).", {"count": i}, ["count"]),
        _fn("set_slowmode", "[admin] Set this channel's slowmode in seconds (0 clears).", {"seconds": i}, ["seconds"]),
    ]


class ToolContext:
    """is_admin gate + a name -> async handler map provided by the caller (cog or test)."""
    def __init__(self, is_admin: bool, handlers: Dict[str, Callable[..., Awaitable]]):
        self.is_admin = is_admin
        self.handlers = handlers


async def dispatch(name: str, raw_args, ctx: ToolContext) -> str:
    if name in ADMIN_TOOLS and not ctx.is_admin:
        return "refused: the requester is not a server admin, so this action is not allowed."
    handler = ctx.handlers.get(name)
    if handler is None:
        return f"refused: unknown or disabled tool '{name}'."
    try:
        args = raw_args if isinstance(raw_args, dict) else json.loads(raw_args or "{}")
    except Exception:
        return "error: could not parse tool arguments."
    try:
        return str(await handler(**args))
    except TypeError as e:
        return f"error: bad arguments ({e})."
    except Exception as e:
        return f"error: {e}"


async def run_agent(client, messages: List[dict], ctx: ToolContext, max_steps: int = 4) -> str:
    """Tool-calling loop: model -> tool_calls -> execute (guarded) -> feed back -> reply."""
    tools = tool_schemas()
    for _ in range(max_steps):
        msg = await client.chat_full(messages, tools=tools)
        calls = msg.get("tool_calls")
        if not calls:
            return (msg.get("content") or "").strip()
        messages.append(msg)
        for tc in calls:
            fn = tc["function"]
            result = await dispatch(fn["name"], fn.get("arguments"), ctx)
            messages.append({"role": "tool", "tool_call_id": tc.get("id", ""), "content": result})
    final = await client.chat_full(messages, tools=None)
    return (final.get("content") or "").strip() or "…"

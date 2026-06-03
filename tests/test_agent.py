"""Agent tests — tool-calling loop (mock OpenAI server) + admin guardrails. Offline."""
import sys, os, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiohttp import web

from agent import dispatch, run_agent, tool_schemas, ToolContext
from llm import LLMClient


def test_tool_schemas_shape():
    names = {t["function"]["name"] for t in tool_schemas()}
    assert {"get_balance", "leaderboard", "timeout_member", "purge_messages"} <= names
    print("ok AG1 tool schemas expose conversation + admin functions")


async def _guardrails():
    calls = []
    async def timeout_member(user_id, minutes, reason="—"):
        calls.append((user_id, minutes)); return f"timed out {user_id} for {minutes}m"
    admin = ToolContext(True, {"timeout_member": timeout_member})
    user = ToolContext(False, {"timeout_member": timeout_member})
    assert "refused" in (await dispatch("timeout_member", '{"user_id":"7","minutes":10}', user)).lower()
    assert calls == []                                   # non-admin never reached the action
    out = await dispatch("timeout_member", '{"user_id":"7","minutes":10}', admin)
    assert calls == [("7", 10)] and "timed out" in out
    print("ok AG2 admin tools refused for non-admins, executed for admins")


async def _agent_loop():
    step = {"n": 0}
    async def handler(request):
        body = await request.json()
        step["n"] += 1
        if step["n"] == 1:                               # first turn: model asks for a tool
            assert "tools" in body
            return web.json_response({"choices": [{"message": {"role": "assistant", "content": None,
                "tool_calls": [{"id": "c1", "type": "function",
                                "function": {"name": "get_balance", "arguments": '{"user_id":"42"}'}}]}}]})
        last = body["messages"][-1]                       # second turn: tool result is present
        assert last["role"] == "tool" and "Ñ" in last["content"]
        return web.json_response({"choices": [{"message": {"role": "assistant",
                "content": f"you have {last['content']}."}}]})

    app = web.Application(); app.router.add_post("/chat/completions", handler)
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", 8911).start()
    try:
        async def get_balance(user_id): return "Ñ7"
        ctx = ToolContext(False, {"get_balance": get_balance})
        client = LLMClient("http://127.0.0.1:8911", "nito", "")
        reply = await run_agent(client, [{"role": "user", "content": "how much do I have?"}], ctx)
        assert reply == "you have Ñ7."
    finally:
        await runner.cleanup()
    print("ok AG3 agent loop: tool_call -> execute -> feed result -> final reply")


def run():
    test_tool_schemas_shape()
    asyncio.run(_guardrails())
    asyncio.run(_agent_loop())


if __name__ == "__main__":
    run()
    print("\nAll NitoBot agent tests passed.")

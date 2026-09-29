"""Optional independent MCP SDK conformance smoke test; required by CI."""

import asyncio
import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp", reason="install .[interop] to run the independent MCP SDK client")
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_official_sdk_can_initialize_list_and_call_stdio(workspace):
    async def check():
        root = Path(__file__).resolve().parents[1]
        env = {**os.environ, "PYTHONPATH": str(root / "src"), "CLAUDECODE": "outer-host"}
        env.pop("AI_ORCHESTRATOR_INTERNAL_WORKER", None)
        params = StdioServerParameters(command=sys.executable, args=["-m", "ai_orchestrator", "--project", str(workspace), "serve"], env=env)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                info = await session.initialize()
                assert info.serverInfo.name == "ai-orchestrator"
                listed = await session.list_tools()
                assert "propose_task" in {tool.name for tool in listed.tools}
                result = await session.call_tool("inspect_project", {})
                assert not result.isError
                assert result.structuredContent["project"] == str(workspace)
                assert result.structuredContent["trusted"] is False
                await session.send_ping()
    asyncio.run(asyncio.wait_for(check(), timeout=20))

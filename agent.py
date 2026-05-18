"""
GenAI4G Agent — LangChain Deep Agent with Claude

A LangGraph ReAct agent powered by Claude (Anthropic API) with MCP server tools.

Usage:
    python agent.py "Your prompt here"
    python agent.py  # interactive mode
"""

import os
import sys
import asyncio
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()  # loads .env into os.environ

from langchain_anthropic import ChatAnthropic
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage, AIMessage

# ---------------------------------------------------------------------------
# Agent configuration
# ---------------------------------------------------------------------------

PROJECT_ROOT = str(Path(__file__).parent.resolve())

MCP_SERVERS = {
    "genai4g": {
        "command": "python",
        "args": ["src/genai4g/server.py"],
        "transport": "stdio",
    }
}

SYSTEM_PROMPT = """\
You are GenAI4G, an expert AI assistant embedded in this project.
You have access to MCP skills from the genai4g server (echo, get_system_info, read_file, list_directory).

Always prefer project-aware, safe operations. Ask for clarification when a
request is ambiguous rather than making assumptions.
"""

model = ChatAnthropic(
    model="claude-opus-4-6",
    api_key=os.environ.get("ANTHROPIC_API_KEY"),
    streaming=True,
)

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


async def run(prompt: str) -> None:
    async with MultiServerMCPClient(MCP_SERVERS) as mcp_client:
        tools = mcp_client.get_tools()
        agent = create_react_agent(model, tools, prompt=SYSTEM_PROMPT)

        print(f"[tools: {[t.name for t in tools]}]\n", flush=True)

        async for event in agent.astream_events(
            {"messages": [HumanMessage(content=prompt)]},
            version="v2",
        ):
            kind = event["event"]
            if kind == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                if chunk.content:
                    text = chunk.content
                    if isinstance(text, list):
                        for part in text:
                            if isinstance(part, dict) and part.get("type") == "text":
                                print(part["text"], end="", flush=True)
                    else:
                        print(text, end="", flush=True)
            elif kind == "on_tool_start":
                tool_name = event.get("name", "")
                print(f"\n[tool: {tool_name}]", flush=True)
            elif kind == "on_tool_end":
                print()  # newline after tool output

        print()  # trailing newline


def interactive() -> None:
    print("GenAI4G Agent (LangChain) — type your prompt and press Enter (Ctrl-C to quit)\n")
    while True:
        try:
            prompt = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nBye.")
            break
        if not prompt:
            continue
        asyncio.run(run(prompt))
        print()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        asyncio.run(run(" ".join(sys.argv[1:])))
    else:
        interactive()

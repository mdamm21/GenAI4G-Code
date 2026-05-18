"""
GenAI4G MCP Server

Exposes skills (tools) to Claude via the Model Context Protocol.
Start with:  python src/genai4g/server.py
"""

import os
import platform
import sys

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("genai4g")


@mcp.tool()
def echo(text: str) -> str:
    """Return the input text unchanged. Useful for testing connectivity."""
    return text


@mcp.tool()
def get_system_info() -> dict:
    """Return basic information about the runtime environment."""
    return {
        "platform": platform.system(),
        "python_version": sys.version,
        "cwd": os.getcwd(),
    }


@mcp.tool()
def read_file(path: str) -> str:
    """Read the contents of a file relative to the project root."""
    safe_path = os.path.normpath(path)
    if os.path.isabs(safe_path) or safe_path.startswith(".."):
        raise ValueError(f"Path must be relative and within the project root: {path}")
    with open(safe_path, "r", encoding="utf-8") as f:
        return f.read()


@mcp.tool()
def list_directory(path: str = ".") -> str:
    """List files and directories at the given path (relative to project root)."""
    safe_path = os.path.normpath(path)
    if os.path.isabs(safe_path) or safe_path.startswith(".."):
        raise ValueError(f"Path must be relative and within the project root: {path}")
    entries = sorted(os.listdir(safe_path))
    return "\n".join(entries)


if __name__ == "__main__":
    mcp.run()

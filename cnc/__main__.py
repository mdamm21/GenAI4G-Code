"""Allow `python -m cnc.server` by forwarding to the server module."""
from cnc.server import mcp

if __name__ == "__main__":
    mcp.run(transport="stdio")

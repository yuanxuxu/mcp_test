# Simple MCP Demo (Python)

This repository contains a minimal Model Context Protocol (MCP) server and a small client that talk over TCP using JSON-RPC 2.0 frames (`Content-Length` headers). The server exposes two simple tools to read and search a text file.

## Files

- `mcp_server.py` — MCP server exposing `read_file` and `search_file` tools.
- `mcp_client.py` — CLI client that connects to the server and invokes tools.
- `context.txt` — Sample text file used by default.

## Requirements

- Python 3.8+ (no external dependencies)
- macOS, Linux, or Windows

Optional but recommended:
- A virtual environment (`python3 -m venv .venv`)

## Quick Start

1) (Optional) create and activate a virtual environment

- macOS/Linux: `python3 -m venv .venv && source .venv/bin/activate`
- Windows (PowerShell): `python -m venv .venv; .\.venv\Scripts\Activate.ps1`

2) Start the server (defaults to 127.0.0.1:8765)

- `python3 mcp_server.py`

3) Run the client in interactive mode (connects to 127.0.0.1:8765 by default)

- `python3 mcp_client.py --repl`

Type `read` to print the current context file, or `search <words>` to find matches. Use `quit` to exit.

4) Run the client in read mode

- `python3 mcp_client.py read`

This prints the contents of `context.txt` and logs the available tools to stderr (e.g., `Tools: read_file, search_file`).

5) Search within the file

- `python3 mcp_client.py search MCP`

This returns the matching lines with line numbers.

## Choose the file to read/search

By default the server reads `context.txt` in this directory. To point at a different file, set `MCP_CONTEXT_FILE` in the server environment before starting it:

- macOS/Linux: `export MCP_CONTEXT_FILE=/absolute/path/to/your.txt && python3 mcp_server.py`
- Windows (PowerShell): `$env:MCP_CONTEXT_FILE='C:\\path\\to\\your.txt'; python mcp_server.py`

Alternatively, edit `context.txt` directly.

## TCP Defaults

- The server listens on `127.0.0.1:8765` by default. Override with `--tcp HOST:PORT`.
- The client connects to `127.0.0.1:8765` by default. Override with `--tcp HOST:PORT`.

Notes:
- `--tcp :8765` is also supported and defaults to `127.0.0.1`.
- The server responds to `shutdown` per-connection; to stop the server, press Ctrl+C in its terminal.

## Notes

- Client and server communicate over TCP using JSON-RPC 2.0 with `Content-Length` framed messages.
- The client automatically sends `shutdown` to the server on exit.

## Troubleshooting

- "Please provide a search query." — Supply a term: `python3 mcp_client.py search term`.
- "File not found" — Check `MCP_CONTEXT_FILE` or ensure `context.txt` exists.
- On Windows, you may use `py -3 mcp_client.py read` if `python3` is unavailable.

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

## How It Works

- Minimal MCP server: `mcp_server.py` implements a tiny Model Context Protocol server that exposes two tools: `read_file` and `search_file`. It handles MCP-style JSON-RPC methods: `initialize`, `tools/list`, `tools/call`, and `shutdown`.
- Small client: `mcp_client.py` connects to the server and invokes those tools either once (one-shot modes) or via a simple REPL.

Transport and framing (TCP + JSON-RPC frames)
- Over TCP: The server listens on `127.0.0.1:8765` by default, and the client connects to that address (both overridable with `--tcp HOST:PORT`).
- JSON-RPC 2.0 messages: Requests/responses are JSON objects with `jsonrpc`, `id`, and either `method` or `result`/`error`.
- Framing via `Content-Length`: Each message is sent as a frame: a header line `Content-Length: N`, a blank line, then N bytes of JSON. This provides unambiguous message boundaries over TCP.
  - Reading frames: `_read_headers` parses headers until a blank line; `read_message` reads exactly `Content-Length` bytes and JSON-decodes (implemented in both client and server).
  - Writing frames: `write_message` JSON-encodes the payload, prepends `Content-Length`, writes, and flushes (implemented in both client and server).

Available tools
- `read_file`: Returns the contents of the configured text file (`context.txt` by default, override with `MCP_CONTEXT_FILE` or pass `path`).
- `search_file`: Returns matching lines (with numbers) that contain the query string.

On-the-wire example
- Request
  - `Content-Length: 95`
  - `{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}`
- Response
  - `Content-Length: <N>`
  - `{"jsonrpc":"2.0","id":1,"result":{"tools":[...]}}`

Code pointers
- Framing helpers: `_read_headers`, `read_message`, `write_message` in both `mcp_server.py` and `mcp_client.py`.
- Server TCP loop: `serve_tcp()` in `mcp_server.py` accepts a connection, wraps it in buffered streams, and handles messages.
- Client call flow: `MCPClient.call()` sends a request and waits for the response with the matching `id`.

## Troubleshooting

- "Please provide a search query." — Supply a term: `python3 mcp_client.py search term`.
- "File not found" — Check `MCP_CONTEXT_FILE` or ensure `context.txt` exists.
- On Windows, you may use `py -3 mcp_client.py read` if `python3` is unavailable.

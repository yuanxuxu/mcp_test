#!/usr/bin/env python3
import json
import os
import sys
import socket
import argparse
from typing import Optional, Dict, Any, Tuple


def log(msg: str) -> None:
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()


def _read_headers(stream) -> Optional[Dict[str, str]]:
    headers = {}
    while True:
        line = stream.readline()
        if not line:
            return None
        try:
            s = line.decode("utf-8")
        except Exception:
            s = str(line)
        s = s.rstrip("\r\n")
        if s == "":
            break
        if ":" in s:
            k, v = s.split(":", 1)
            headers[k.strip().lower()] = v.strip()
    return headers


def read_message(stream) -> Optional[Dict[str, Any]]:
    headers = _read_headers(stream)
    if headers is None:
        return None
    if "content-length" not in headers:
        return None
    try:
        length = int(headers["content-length"])
    except ValueError:
        return None
    payload = stream.read(length)
    if not payload:
        return None
    try:
        return json.loads(payload.decode("utf-8"))
    except Exception as e:
        log(f"Failed to parse JSON payload: {e}")
        return None


def write_message(stream, message: Dict[str, Any]) -> None:
    data = json.dumps(message, separators=(",", ":")).encode("utf-8")
    header = f"Content-Length: {len(data)}\r\n\r\n".encode("utf-8")
    stream.write(header)
    stream.write(data)
    stream.flush()


CONTEXT_FILE = os.environ.get(
    "MCP_CONTEXT_FILE", os.path.join(os.path.dirname(__file__), "context.txt")
)


def read_context(path: Optional[str] = None) -> str:
    p = path or CONTEXT_FILE
    with open(p, "r", encoding="utf-8") as f:
        return f.read()


def search_context(words: str, path: Optional[str] = None) -> str:
    query = words.strip()
    if not query:
        return ""
    text = read_context(path)
    lines = text.splitlines()
    q = query.lower()
    matches = []
    for idx, line in enumerate(lines, start=1):
        if q in line.lower():
            matches.append((idx, line))
    if not matches:
        return f"No matches for: {query}"
    out = [f"Matches ({len(matches)}) for: {query}"]
    for n, l in matches:
        out.append(f"{n}: {l}")
    return "\n".join(out)


def handle_initialize(req_id: int) -> Dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "SimpleMCP-Server", "version": "0.1.0"},
            "capabilities": {"tools": {}},
        },
    }


def handle_tools_list(req_id: int) -> Dict[str, Any]:
    tools = [
        {
            "name": "read_file",
            "description": "Read the configured context file (or an optional path).",
            "input_schema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
            },
        },
        {
            "name": "search_file",
            "description": "Search for words in the context file and return matching lines.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "words": {"type": "string", "description": "Search string"},
                    "path": {"type": "string"},
                },
                "required": ["words"],
            },
        },
    ]
    return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools}}


def handle_tools_call(req_id: int, params: Dict[str, Any]) -> Dict[str, Any]:
    name = params.get("name")
    arguments = params.get("arguments") or {}

    try:
        if name == "read_file":
            path = arguments.get("path")
            content = read_context(path)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {"type": "text", "text": content},
                    ]
                },
            }
        elif name == "search_file":
            words = arguments.get("words") or arguments.get("query") or ""
            path = arguments.get("path")
            found = search_context(str(words), path)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {"type": "text", "text": found},
                    ]
                },
            }
        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: tool {name}",
                },
            }
    except FileNotFoundError as e:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32000, "message": f"File not found: {e}"},
        }
    except Exception as e:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32001, "message": f"Server error: {e}"},
        }

def handle_connection(read_stream, write_stream) -> None:
    while True:
        msg = read_message(read_stream)
        if msg is None:
            break
        if not isinstance(msg, dict):
            continue
        method = msg.get("method")
        req_id = msg.get("id")
        params = msg.get("params") or {}

        if method == "initialize":
            write_message(write_stream, handle_initialize(req_id))
        elif method == "tools/list":
            write_message(write_stream, handle_tools_list(req_id))
        elif method == "tools/call":
            write_message(write_stream, handle_tools_call(req_id, params))
        elif method in ("shutdown", "exit"):
            # Respond OK to shutdown and then close this connection
            if req_id is not None:
                write_message(write_stream, {"jsonrpc": "2.0", "id": req_id, "result": {}})
            break
        else:
            if req_id is not None:
                write_message(
                    write_stream,
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {
                            "code": -32601,
                            "message": f"Method not found: {method}",
                        },
                    },
                )


def parse_host_port(spec: str) -> Tuple[str, int]:
    s = spec.strip()
    if not s:
        raise ValueError("Empty host:port")
    if s.startswith(":"):
        host = "127.0.0.1"
        port_s = s[1:]
    else:
        if ":" not in s:
            raise ValueError("Expected HOST:PORT or :PORT")
        host, port_s = s.rsplit(":", 1)
    port = int(port_s)
    return host, port


def serve_stdio() -> None:
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer
    handle_connection(stdin, stdout)


def serve_tcp(addr: str) -> None:
    host, port = parse_host_port(addr)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((host, port))
        srv.listen(8)
        log(f"MCP server listening on {host}:{port}")
        while True:
            conn, (peer_host, peer_port) = srv.accept()
            log(f"Accepted connection from {peer_host}:{peer_port}")
            try:
                r = conn.makefile("rb")
                w = conn.makefile("wb")
                try:
                    handle_connection(r, w)
                finally:
                    try:
                        r.close()
                    except Exception:
                        pass
                    try:
                        w.close()
                    except Exception:
                        pass
            finally:
                try:
                    conn.close()
                except Exception:
                    pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Simple MCP Server")
    parser.add_argument(
        "--tcp",
        metavar="HOST:PORT",
        help="Listen on TCP (default: 127.0.0.1:8765).",
    )
    args = parser.parse_args()
    addr = args.tcp or "127.0.0.1:8765"
    serve_tcp(addr)


if __name__ == "__main__":
    main()

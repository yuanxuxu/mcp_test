#!/usr/bin/env python3
import json
import os
import subprocess
import socket
import argparse
import sys
from typing import Dict, Any, Optional, Tuple


def log(msg: str) -> None:
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()


def _read_headers(stream) -> Optional[Dict[str, str]]:
    headers = {}
    while True:
        line = stream.readline()
        if not line:
            return None
        s = line.decode("utf-8").rstrip("\r\n")
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
    length = int(headers["content-length"])
    payload = stream.read(length)
    if not payload:
        return None
    return json.loads(payload.decode("utf-8"))


def write_message(stream, message: Dict[str, Any]) -> None:
    data = json.dumps(message, separators=(",", ":")).encode("utf-8")
    header = f"Content-Length: {len(data)}\r\n\r\n".encode("utf-8")
    stream.write(header)
    stream.write(data)
    stream.flush()


class MCPClient:
    def __init__(self, server_cmd: Optional[list] = None, tcp_addr: Optional[str] = None):
        self.proc: Optional[subprocess.Popen] = None
        self.sock: Optional[socket.socket] = None
        self.inp = None
        self.out = None
        self._id = 0

        if tcp_addr:
            host, port = self._parse_host_port(tcp_addr)
            self.sock = socket.create_connection((host, port))
            # Use file-like interfaces for framed IO
            self.inp = self.sock.makefile("rb")
            self.out = self.sock.makefile("wb")
        else:
            if not server_cmd:
                raise ValueError("server_cmd is required when tcp_addr is not provided")
            env = os.environ.copy()
            self.proc = subprocess.Popen(
                server_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
                env=env,
            )
            assert self.proc.stdin and self.proc.stdout
            self.inp = self.proc.stdout
            self.out = self.proc.stdin

    @staticmethod
    def _parse_host_port(spec: str) -> Tuple[str, int]:
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
        return host, int(port_s)

    def next_id(self) -> int:
        self._id += 1
        return self._id

    def call(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        req_id = self.next_id()
        write_message(self.out, {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
        # Read messages until matching id (simple serial usage)
        while True:
            msg = read_message(self.inp)
            if msg is None:
                raise RuntimeError("Server terminated or sent invalid message")
            if msg.get("id") == req_id:
                return msg

    def close(self) -> None:
        try:
            if self.out is not None:
                write_message(self.out, {"jsonrpc": "2.0", "id": self.next_id(), "method": "shutdown", "params": {}})
        except Exception:
            pass
        # Close transport
        if self.proc is not None:
            try:
                self.proc.terminate()
            except Exception:
                pass
        if self.sock is not None:
            try:
                try:
                    self.out.flush()  # type: ignore[union-attr]
                except Exception:
                    pass
                try:
                    self.inp.close()  # type: ignore[union-attr]
                except Exception:
                    pass
                try:
                    self.out.close()  # type: ignore[union-attr]
                except Exception:
                    pass
                self.sock.close()
            except Exception:
                pass


def print_content_result(result: Dict[str, Any]) -> None:
    res = result.get("result") or {}
    content = res.get("content") or []
    printed = False
    for part in content:
        if isinstance(part, dict) and part.get("type") == "text":
            sys.stdout.write(part.get("text", ""))
            sys.stdout.write("\n")
            printed = True
    if not printed:
        # Fallback: pretty print whole result
        sys.stdout.write(json.dumps(res, indent=2) + "\n")


def _interactive_loop(client: "MCPClient") -> int:
    sys.stderr.write("Entering interactive mode.\n")
    sys.stderr.write("Commands: read [path] | search <words> | tools | help | quit\n")
    sys.stderr.flush()

    while True:
        try:
            line = input("> ").strip()
        except EOFError:
            sys.stderr.write("\n")
            return 0
        except KeyboardInterrupt:
            sys.stderr.write("\n")
            return 0

        if not line:
            continue
        parts = line.split()
        cmd = parts[0].lower()
        args = parts[1:]

        if cmd in ("quit", "exit"):
            return 0
        if cmd in ("help", "h", "?"):
            sys.stderr.write("Commands: read [path] | search <words> | tools | help | quit\n")
            sys.stderr.flush()
            continue
        if cmd == "tools":
            tools = client.call("tools/list", {})
            tool_names = [t.get("name") for t in (tools.get("result", {}).get("tools", []) or [])]
            sys.stderr.write("Tools: " + ", ".join(tool_names) + "\n")
            sys.stderr.flush()
            continue
        if cmd == "read":
            path = args[0] if args else None
            res = client.call("tools/call", {"name": "read_file", "arguments": ({"path": path} if path else {})})
            print_content_result(res)
            continue
        if cmd == "search":
            if not args:
                sys.stderr.write("Usage: search <words>\n")
                sys.stderr.flush()
                continue
            query = " ".join(args)
            res = client.call("tools/call", {"name": "search_file", "arguments": {"words": query}})
            print_content_result(res)
            continue

        sys.stderr.write(f"Unknown command: {cmd}. Type 'help' for options.\n")
        sys.stderr.flush()


def main(argv):
    # Usage: mcp_client.py [--tcp HOST:PORT] [--repl|repl] [read|search] [query]
    parser = argparse.ArgumentParser(description="Simple MCP Client")
    parser.add_argument("--tcp", metavar="HOST:PORT", help="Connect to a TCP server (default: 127.0.0.1:8765).")
    parser.add_argument("mode", nargs="?", default=None, choices=["read", "search", "repl", "interactive"], help="Operation mode")
    parser.add_argument("query", nargs="?", help="Query text for search mode")
    parser.add_argument("--repl", action="store_true", help="Enter interactive mode and accept multiple commands.")
    args = parser.parse_args(argv[1:])

    tcp_target = args.tcp or "127.0.0.1:8765"
    client: Optional[MCPClient] = None
    try:
        client = MCPClient(server_cmd=None, tcp_addr=tcp_target)
    except Exception as e:
        sys.stderr.write(f"Failed to connect to {tcp_target}: {e}\n")
        sys.stderr.write("Start the server with: python3 mcp_server.py\n")
        return 2
    try:
        init = client.call("initialize", {"clientInfo": {"name": "SimpleMCP-Client", "version": "0.1.0"}})
        tools = client.call("tools/list", {})
        # Print the tool names for visibility
        tool_names = [t.get("name") for t in (tools.get("result", {}).get("tools", []) or [])]
        sys.stderr.write("Tools: " + ", ".join(tool_names) + "\n")
        sys.stderr.flush()

        # Decide interactive vs one-shot
        if args.repl or (args.mode in ("repl", "interactive")):
            return _interactive_loop(client)

        # One-shot modes preserved for compatibility
        if args.mode == "read" or (args.mode is None and args.query is None):
            res = client.call("tools/call", {"name": "read_file", "arguments": {}})
            print_content_result(res)
            return 0
        if args.mode == "search":
            if not args.query:
                sys.stderr.write("Please provide a search query.\n")
                return 2
            res = client.call("tools/call", {"name": "search_file", "arguments": {"words": args.query}})
            print_content_result(res)
            return 0

        # If we get here, mode was unrecognized
        sys.stderr.write(f"Unknown or incomplete arguments. Use --repl or modes: read|search.\n")
        return 2
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

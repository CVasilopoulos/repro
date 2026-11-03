import asyncio
import ipaddress
import json
import os
import socket
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

DEFAULT_ALLOW = (
    "github.com,codeload.github.com,objects.githubusercontent.com,raw.githubusercontent.com,"
    "pypi.org,files.pythonhosted.org,registry.npmjs.org,proxy.golang.org,sum.golang.org,"
    "static.crates.io,index.crates.io"
)
ALLOWED_PORTS = {80, 443}
METADATA_IPS = {ipaddress.ip_address("169.254.169.254"), ipaddress.ip_address("fd00:ec2::254")}


@dataclass
class Decision:
    allowed: bool
    reason: str
    address: str = ""


def parse_allowlist(raw: str) -> list[str]:
    return [h.strip().lower().rstrip(".") for h in raw.split(",") if h.strip()]


def host_allowed(host: str, allow: list[str]) -> bool:
    host = host.lower().rstrip(".")
    return any(host == a or host.endswith("." + a) for a in allow)


def classify_ip(ip: ipaddress._BaseAddress) -> str | None:
    if ip in METADATA_IPS:
        return "cloud metadata endpoint"
    if ip.is_loopback:
        return "loopback address"
    if ip.is_link_local:
        return "link-local address"
    if ip.is_private:
        return "private address"
    if ip.is_multicast or ip.is_reserved or ip.is_unspecified or not ip.is_global:
        return "non-public address"
    return None


def literal_ip(host: str) -> ipaddress._BaseAddress | None:
    try:
        return ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return None


def decide(host: str, port: int, allow: list[str], resolve) -> Decision:
    ip = literal_ip(host)
    if ip is not None:
        why = classify_ip(ip)
        return Decision(False, why or "raw IP address (only allowlisted hostnames)")
    if port not in ALLOWED_PORTS:
        return Decision(False, f"port {port} not allowed")
    if not host_allowed(host, allow):
        return Decision(False, "host not on the allowlist")
    try:
        addresses = resolve(host, port)
    except OSError as exc:
        return Decision(False, f"DNS failure: {exc}")
    if not addresses:
        return Decision(False, "DNS returned no addresses")
    for addr in addresses:
        why = classify_ip(ipaddress.ip_address(addr))
        if why:
            return Decision(False, f"{host} resolves to {why} {addr}")
    return Decision(True, "allowlisted", addresses[0])


def system_resolve(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    seen = []
    for info in infos:
        addr = info[4][0]
        if addr not in seen:
            seen.append(addr)
    return seen


class Ledger:
    def __init__(self, path: str | None):
        self.path = path

    def write(self, entry: dict) -> None:
        line = json.dumps(entry, sort_keys=True)
        print(line, flush=True)
        if self.path:
            try:
                with open(self.path, "a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
            except OSError as exc:
                print(json.dumps({"ledger_error": str(exc)}), flush=True)


class Gate:
    def __init__(self, allow: list[str], ledger: Ledger, resolve=system_resolve, idle_timeout: float = 120.0):
        self.allow = allow
        self.ledger = ledger
        self.resolve = resolve
        self.idle_timeout = idle_timeout

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        src = peer[0] if peer else "?"
        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=30)
        except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, asyncio.TimeoutError, ConnectionError):
            writer.close()
            return
        lines = head.decode("latin-1").split("\r\n")
        try:
            method, target, version = lines[0].split(" ", 2)
        except ValueError:
            await self.reply(writer, 400, "bad request line")
            return
        method = method.upper()
        if method == "CONNECT":
            host, _, port_s = target.rpartition(":")
            port = int(port_s) if port_s.isdigit() else 443
            host = host.strip("[]")
            url = target
        else:
            parts = urlsplit(target)
            if parts.scheme != "http" or not parts.hostname:
                await self.reply(writer, 400, "only absolute http:// URLs or CONNECT")
                return
            host, port, url = parts.hostname, parts.port or 80, target
        loop = asyncio.get_running_loop()
        decision = await loop.run_in_executor(None, decide, host, port, self.allow, self.resolve)
        entry = {
            "ts": time.time(),
            "src": src,
            "method": method,
            "host": host,
            "port": port,
            "url": url[:300],
            "allowed": decision.allowed,
            "reason": decision.reason,
        }
        if not decision.allowed:
            self.ledger.write(entry)
            await self.reply(writer, 403, f"repro egress gate: {decision.reason}")
            return
        try:
            up_reader, up_writer = await asyncio.wait_for(
                asyncio.open_connection(decision.address, port), timeout=15
            )
        except (OSError, asyncio.TimeoutError) as exc:
            entry.update(allowed=False, reason=f"upstream connect failed: {exc}")
            self.ledger.write(entry)
            await self.reply(writer, 502, "upstream connect failed")
            return
        self.ledger.write(entry)
        if method == "CONNECT":
            writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
            await writer.drain()
        else:
            up_writer.write(self.rewrite_request(lines, head))
            await up_writer.drain()
        await asyncio.gather(
            self.pipe(reader, up_writer), self.pipe(up_reader, writer), return_exceptions=True
        )

    @staticmethod
    def rewrite_request(lines: list[str], head: bytes) -> bytes:
        method, target, version = lines[0].split(" ", 2)
        parts = urlsplit(target)
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        kept = [l for l in lines[1:] if l and not l.lower().startswith(("proxy-", "connection:"))]
        out = [f"{method} {path} {version}"] + kept + ["Connection: close", "", ""]
        return "\r\n".join(out).encode("latin-1")

    async def pipe(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while True:
                data = await asyncio.wait_for(reader.read(65536), timeout=self.idle_timeout)
                if not data:
                    break
                writer.write(data)
                await writer.drain()
        finally:
            try:
                writer.close()
            except Exception:
                pass

    @staticmethod
    async def reply(writer: asyncio.StreamWriter, status: int, text: str) -> None:
        reason = {400: "Bad Request", 403: "Forbidden", 502: "Bad Gateway"}.get(status, "Error")
        body = (text + "\n").encode()
        writer.write(
            f"HTTP/1.1 {status} {reason}\r\nContent-Type: text/plain\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode()
            + body
        )
        try:
            await writer.drain()
        finally:
            writer.close()


async def main() -> None:
    allow = parse_allowlist(os.environ.get("GATE_ALLOW", DEFAULT_ALLOW))
    ledger = Ledger(os.environ.get("GATE_LEDGER"))
    if ledger.path:
        open(ledger.path, "a").close()
    gate = Gate(allow, ledger)
    port = int(os.environ.get("GATE_PORT", "3128"))
    server = await asyncio.start_server(gate.handle, "0.0.0.0", port)
    print(json.dumps({"gate": "listening", "port": port, "allow": allow}), flush=True)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())

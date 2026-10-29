"""Opt-in access from a phone on the same network.

The framework listens on loopback and validates Host/Origin by default. The
iOS client runs on another device, so the desktop has to answer requests whose
Host is a local address. Sharing therefore stays opt-in (`--share`) and every
such request must carry the pairing code that the launch window prints; an
unpaired device on the same network cannot read account data.
"""
from __future__ import annotations

import ipaddress
import secrets
import socket
from datetime import datetime, timezone

COOKIE = "campusmate_shared"
MAX_AGE = 31536000
LOCAL_SUFFIXES = (".local", ".lan")


def code(store):
    """Return the saved pairing code, creating it the first time."""
    saved = store.read("share", {})
    value = saved.get("code") if isinstance(saved, dict) else None
    if not isinstance(value, str) or len(value) != 8 or value.lower() != value or not all(character in "0123456789abcdef" for character in value):
        value = secrets.token_hex(4)
        store.write("share", {"code": value, "created_at": datetime.now(timezone.utc).isoformat()})
    return value


def loopback(port):
    return {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}


def address(host, port):
    """True when a Host header names this device on the local network."""
    name, _, value = host.rpartition(":")
    if not name or value != str(port):
        return False
    name = name.strip("[]").lower()
    if name.endswith(LOCAL_SUFFIXES):
        return True
    try:
        return ipaddress.ip_address(name).is_private
    except ValueError:
        return False


def urls(port):
    """Every address a phone can reach, LAN first so the last line is the hint."""
    found = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET, socket.SOCK_STREAM):
            found.add(info[4][0])
    except OSError:
        pass
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Connecting a UDP socket only asks the routing table for the local address.
        probe.connect(("192.0.2.1", 9))
        found.add(probe.getsockname()[0])
    except OSError:
        pass
    finally:
        probe.close()
    reachable = []
    for value in found:
        try:
            parsed = ipaddress.ip_address(value)
        except ValueError:
            continue
        if parsed.version == 4 and parsed.is_private and not parsed.is_loopback:
            reachable.append(value)
    return [f"http://{value}:{port}" for value in sorted(reachable, key=lambda value: ipaddress.ip_address(value))]

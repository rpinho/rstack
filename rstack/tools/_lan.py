"""Bounded system IPv4 resolution shared by LAN health and the proposed pf refresher."""
import ipaddress
import json
import socket
import subprocess
import sys


LAN = ipaddress.ip_network('192.168.86.0/24')


def resolve_ipv4(host, timeout=3):
    # getaddrinfo has no libc deadline. A short-lived subprocess can actually be
    # killed and reaped on timeout, unlike a background resolver thread.
    result = subprocess.run([sys.executable, '-c',
        'import json,socket,sys; print(json.dumps(sorted({a[4][0] for a in '
        'socket.getaddrinfo(sys.argv[1],0,socket.AF_INET,socket.SOCK_STREAM)})))', host],
        capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise OSError('IPv4 resolution failed for ' + host)
    addresses = json.loads(result.stdout)
    if not addresses:
        raise OSError('no IPv4 addresses for ' + host)
    return addresses


def home_lan_addresses(addresses):
    return sorted({str(ipaddress.IPv4Address(address)) for address in addresses
                   if ipaddress.IPv4Address(address) in LAN
                   and ipaddress.IPv4Address(address) not in (LAN.network_address, LAN.broadcast_address)})

import socket, struct, random, time

def dns_query_raw(ip, name=b"google.com"):
    tid = random.randint(0, 0xFFFF)
    header = struct.pack(">HHHHHH", tid, 0x0100, 1, 0, 0, 0)
    q = b"".join(bytes([len(part)]) + part for part in name.split(b".")) + b"\x00" + struct.pack(">HH", 1, 1)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(2)
    try:
        s.sendto(header + q, (ip, 53))
        data, _ = s.recvfrom(512)
        flags = struct.unpack(">H", data[2:4])[0]
        rcode = flags & 0xF
        ancount = struct.unpack(">H", data[6:8])[0]
        ns = struct.unpack(">H", data[8:10])[0]
        rcodes = {0:"NOERROR",1:"FORMERR",2:"SERVFAIL",3:"NXDOMAIN",4:"NOTIMP",5:"REFUSED"}
        print(f"  DNS {ip}: rcode={rcodes.get(rcode, rcode)} answers={ancount} ns={ns} len={len(data)}")
    except socket.timeout:
        print(f"  DNS {ip}: TIMEOUT")
    except Exception as e:
        print(f"  DNS {ip}: ERR {e}")

def tcp_banner(ip, port, payload=None, timeout=2.5):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((ip, port))
        out = b""
        s.settimeout(1.2)
        if payload:
            s.sendall(payload)
        try:
            out = s.recv(4096)
        except Exception:
            pass
        desc = out[:200].decode("latin-1", "replace").replace("\r", "\\r").replace("\n", "\\n")
        print(f"  TCP {ip}:{port} -> CONNECTED, {len(out)} bytes: {desc[:150]}")
    except socket.timeout:
        print(f"  TCP {ip}:{port} -> TIMEOUT")
    except Exception as e:
        print(f"  TCP {ip}:{port} -> {type(e).__name__}: {e}")
    finally:
        s.close()

http_get = b"GET / HTTP/1.1\r\nHost: %s\r\nUser-Agent: FreebuffProbe/1.0\r\nAccept: */*\r\nConnection: close\r\n\r\n"

print("### A) DNS sanity: nonexistent & control hosts")
for ip in ["172.16.60.60", "172.16.199.199", "192.168.77.88", "10.255.255.1", "172.16.25.1"]:
    dns_query_raw(ip)

print("\n### B) TCP to target devices: HTTP & attendance ports")
targets = ["172.16.50.30", "172.16.8.20", "172.16.0.20", "172.16.32.21"]
for ip in targets:
    print(f"-- {ip} --")
    tcp_banner(ip, 80, http_get % ip.encode())
    tcp_banner(ip, 4370)
    tcp_banner(ip, 8080, http_get % ip.encode())
    tcp_banner(ip, 443)

print("\n### C) TCP to nonexistent hosts on same style (control)")
for ip in ["172.16.60.60", "172.16.199.199"]:
    print(f"-- {ip} --")
    tcp_banner(ip, 80, http_get % ip.encode(), timeout=2)
    tcp_banner(ip, 4370, None, timeout=2)
    tcp_banner(ip, 53, None, timeout=2)

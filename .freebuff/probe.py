import socket, sys, concurrent.futures

IPs = ["172.16.50.30", "172.16.8.20", "172.16.0.20", "172.16.32.21"]
PORTS = [21, 22, 23, 53, 80, 443, 554, 8000, 8080, 8081, 8443, 4370, 5005, 5007, 5010, 6000, 6001, 1234, 1433, 3306, 5432]

def probe(ip_port):
    ip, port = ip_port
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1.5)
    try:
        s.connect((ip, port))
        # try to grab a banner quickly
        banner = b""
        try:
            s.settimeout(0.6)
            banner = s.recv(256)
        except Exception:
            pass
        return (ip, port, True, banner)
    except Exception as e:
        return (ip, port, False, b"")
    finally:
        s.close()

tasks = [(ip, p) for ip in IPs for p in PORTS]
with concurrent.futures.ThreadPoolExecutor(max_workers=40) as ex:
    results = list(ex.map(probe, tasks))

for ip in IPs:
    print(f"=== {ip} ===")
    for (i, p, ok, banner) in results:
        if i == ip and ok:
            b = banner[:80].decode("latin-1", "replace").replace("\r", "\\r").replace("\n", "\\n")
            print(f"  OPEN {p}: {b}")

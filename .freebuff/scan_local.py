import socket, concurrent.futures, ipaddress, struct

SUBNET = "172.16.25.0/24"
PORTS = [22, 23, 53, 80, 443, 554, 8000, 8080, 8081, 4370, 5005, 5007, 5010, 6000, 6001]

def probe(args):
    ip, port = args
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.4)
    try:
        s.connect((ip, port))
        return (ip, port, True)
    except Exception:
        return (ip, port, False)
    finally:
        s.close()

hosts = [str(ip) for ip in ipaddress.ip_network(SUBNET, strict=False).hosts()]
print(f"Scanning {SUBNET}: {len(hosts)} hosts x {len(PORTS)} ports (light)")

open_map = {}
with concurrent.futures.ThreadPoolExecutor(max_workers=128) as ex:
    results = ex.map(probe, [(h, p) for h in hosts for p in PORTS])
    for ip, port, ok in results:
        if ok:
            open_map.setdefault(ip, []).append(port)

for ip in sorted(open_map):
    print(f"{ip}: {sorted(open_map[ip])}")
print("done")

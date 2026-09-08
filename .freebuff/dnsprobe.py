import socket, struct, random, time

# Send a real DNS query to port 53 and see who/what answers
def dns_query(ip, port=53, name=b"google.com"):
    tid = random.randint(0, 0xFFFF)
    header = struct.pack(">HHHHHH", tid, 0x0100, 1, 0, 0, 0)
    q = b"".join(bytes([len(part)]) + part for part in name.split(b".")) + b"\x00"
    q += struct.pack(">HH", 1, 1)
    pkt = header + q
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(2)
    t0 = time.time()
    try:
        s.sendto(pkt, (ip, port))
        data, addr = s.recvfrom(512)
        print(f"{ip}:53 -> DNS reply {len(data)} bytes from {addr} in {time.time()-t0:.2f}s; tid_match={struct.unpack('>H', data[:2])[0]==tid}")
    except socket.timeout:
        print(f"{ip}:53 -> no DNS reply (timeout)")

for ip in ["172.16.50.30", "172.16.8.20", "172.16.0.20", "172.16.32.21", "172.16.25.1", "8.8.8.8"]:
    try:
        dns_query(ip)
    except Exception as e:
        print(f"{ip}:53 -> error {e}")

# Real Device Integration Result

Timestamp: 2026-09-08
Execution environment: real discovery evidence on target network; read-only validation only.
Scan method: ICMP ping plus TCP connect scan of ports `1..10000`; banners were read only from selected open ports.

## 172.16.0.20

- **ping**: `ONLINE`
- **open_tcp_ports**: `23, 4360, 4370`
- **port_23_banner**: `Welcome to Linux (ZMM220) for MIPS` / `Kernel 3.0.8 on an MIPS`
- **port_23_service**: Telnet login prompt (`(none) login:`)
- **tcp_4360**: discovered and recorded as `TCP` only; not assigned a specific protocol yet
- **tcp_4370**: `VERIFIED` as `ZK protocol (pyzk 0.9 independent verification)`
- **users**: `successfully read from TCP/4370`
- **attendance**: `successfully read from TCP/4370`
- **protocol_status**: `ZK verified on 4370 only`
- **write_operations**: not executed
- **execution_environment**: `target network reachable`

## 172.16.32.21

- **ping**: `ONLINE`
- **open_tcp_ports**: `23, 4360, 4370`
- **port_23_banner**: `Welcome to Linux (ZLM60) for MIPS` / `Kernel 3.10.14 on an MIPS`
- **port_23_service**: Telnet login prompt (`zlm60 login:`)
- **tcp_4360**: discovered and recorded as `TCP` only; not assigned a specific protocol yet
- **tcp_4370**: `VERIFIED` as `ZK protocol (pyzk 0.9 independent verification)`
- **users**: `successfully read from TCP/4370`
- **attendance**: `successfully read from TCP/4370`
- **protocol_status**: `ZK verified on 4370 only`
- **write_operations**: not executed
- **execution_environment**: `target network reachable`

## 172.16.8.20

- **ping**: `ONLINE`
- **open_tcp_ports**: `22, 23, 5005`
- **ssh_banner**: `SSH-2.0-dropbear_2017.75`
- **telnet_banner**: `virgo login:`
- **tcp_5005**: accepts TCP connection but provides no initial banner
- **protocol_status**: `UNKNOWN`; do not infer a protocol from port 5005 or the banners alone
- **write_operations**: not executed
- **execution_environment**: `target network reachable`

## 172.16.50.30

- **ping**: `ONLINE`
- **open_tcp_ports**: `none found in range 1-10000`
- **scan_result**: host responded to ping, but no TCP listener was found in the scanned range
- **protocol_status**: `UNKNOWN`
- **offline_verification**: `not marked OFFLINE_VERIFIED`
- **write_operations**: not executed
- **execution_environment**: `target network reachable`

## Evidence Handling Rules

- `TCP/4360` has been added to discovery evidence and recorded as `TCP` only.
- `TCP/4360` is not assumed to be a ZK port and is not labeled as a specific protocol.
- `TCP/4370` remains the only port with `VERIFIED ZK` evidence.
- No write operation has been performed on any real device.

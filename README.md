# Distributed Streaming-based Client-Server Collaboration Application

## 1. Project Overview

This project implements an HTTP server application equipped with a chat application built using Python socket programming. The application features multiple server process deployments with a reverse proxy server process and backend server processes, supporting client-server coordination and peer-to-peer (P2P) communication.

---

## 2. System Architecture

### Architectural Layers:
1. **HTTP Reverse Proxy Layer (`daemon/proxy.py`, `start_proxy.py`, `config/proxy.conf`)**:
   - Listens on public interface (default port `8080`).
   - Parses incoming HTTP/1.1 requests, extracts the `Host:` header, and resolves backend targets from virtual host configuration.
   - Dispatches traffic across multiple backend nodes using thread-safe **Round-Robin load balancing**.
   - Handles client connections concurrently using worker threads.
   - Enforces defensive HTTP error handling (`400 Bad Request` on missing headers, `404 Not Found` on unmapped virtual hosts, `502 Bad Gateway` on connection failures).

2. **Backend Application Layer (`daemon/backend.py`, `start_backend.py`, `daemon/httpadapter.py`)**:
   - Core REST application server using the StreapRous socket framework.
   - Dispatches HTTP requests through route hooks and custom adapters with support for raw socket packet capture and kernel RST packet dropping (macOS `pfctl` / Linux `iptables`) as well as standard socket connections on localhost.

3. **Central Tracker & Session Directory (`server/`)**:
   - Manages user accounts, credential verification, and active token-based session leases.
   - Maintains an in-memory directory of active online peers (IP addresses, TCP streaming ports, and UDP file ports).

4. **Client & Peer-to-Peer File Transfer (`client/`)**:
   - Terminal-based interactive client console.
   - Direct peer-to-peer TCP streaming for real-time messaging with sequence ordering and ACK confirmation.
   - High-throughput UDP file transmission partitioning files into 1024-byte binary chunks with metadata framing (UUIDv4 + chunk order) and SHA-256 integrity verification.

5. **Common Protocol Framing & Codecs (`common/`)**:
   - Custom 24-byte binary packet header (`!BBHIIIII`: Version, MessageType, Flags, StreamID, SequenceNumber, SenderID, ReceiverID, PayloadLength).
   - Wire serialization via `PacketCodec` and type-safe JSON DTO codec via `JsonPayloadCodec`.

---

## 3. Getting Started

### Prerequisites
- **Python 3.10+** (Python 3.12 recommended).
- Operating System: **Windows, Linux, or macOS**.
- **No external pip packages required**; the application uses Python's standard library (`socket`, `threading`, `struct`, `hashlib`, `uuid`, `argparse`, `unittest`).

---

## 4. Running the System

### 1. Start the Backend Server
Run one or more backend instances listening on designated ports:
```bash
# Terminal 1 (Backend on port 9000)
python start_backend.py --server-ip 127.0.0.1 --server-port 9000

# Terminal 2 (Optional: Second Backend on port 9001 for load balancing)
python start_backend.py --server-ip 127.0.0.1 --server-port 9001
```

### 2. Configure and Start the HTTP Reverse Proxy
Inspect or modify the routing table in `config/proxy.conf`:
```nginx
host "app1.local" {
    proxy_pass http://127.0.0.1:9000;
}

host "app2.local" {
    proxy_set_header Host $host;
    proxy_pass http://127.0.0.1:9000;
    proxy_pass http://127.0.0.1:9001;
    dist_policy round-robin
}
```

Launch the proxy server:
```bash
# Terminal 3 (Reverse Proxy on port 8080)
python start_proxy.py --server-ip 127.0.0.1 --server-port 8080
```

Test proxy routing and load balancing with `curl`:
```bash
# Request routed to app1.local
curl -H "Host: app1.local" http://127.0.0.1:8080/

# Request routed to app2.local (balances across backends 9000 and 9001)
curl -H "Host: app2.local" http://127.0.0.1:8080/
```

### 3. Start Tracker and Clients
```bash
# Terminal 4: Start central tracker server
python -m server.tracker_server

# Terminal 5: Start Client A
python -m client.client_console

# Terminal 6: Start Client B
python -m client.client_console
```

---

## 5. Verification & Testing

The project includes an automated integration test suite containing **72 test cases** across 6 testing modules.

### Running All Integration Tests:
```bash
# Windows (PowerShell)
$env:PYTHONPATH = "."
python -m unittest discover -s tests -v

# Linux / macOS
PYTHONPATH=. python3 -m unittest discover -s tests -v
```

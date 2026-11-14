# Integration Test Suite Documentation

> **Project:** CO3094 - Computer Networks Assignment 1: Distributed Streaming-based Client-Server Collaboration Application  
> **Author:** P. Tuấn (`tuanphusimon`)  
> **Module:** Integration & System Testing (`tests/`)  
> **Target Framework:** Python 3.10+ Standard Library (`unittest`, `socket`, `struct`)

---

## 1. Overview & Test Architecture

This test suite provides automated integration, protocol verification, boundary, and concurrency testing for the Distributed Streaming Collaboration system. All tests are designed according to standard network programming specifications (RFC 9112 HTTP/1.1 semantics, custom binary wire format specifications, and raw TCP/UDP socket lifecycle management).

### Summary Matrix

| # | Test Module | Target System / Component | Scope & Category | Test Cases | Status |
|---|-------------|---------------------------|------------------|:----------:|:------:|
| 1 | `test_packet_codec.py` | `common/PacketCodec.py`, `PacketHeader.py` | Wire Serialization, Bit Packing, Bounds | 15 | **PASSED** |
| 2 | `test_tcp_connection.py` | Raw TCP Layer, OS Socket Sockets | Handshake, Echo, Graceful Disconnect, EOF | 8 | **PASSED** |
| 3 | `test_http.py` | `daemon/proxy.py`, `start_proxy.py`, `config/proxy.conf` | Virtual Hosts, HTTP Headers, Round-Robin Balancing | 10 | **PASSED** |
| 4 | `test_auth.py` | Login, Signup, Logout payloads | Protocol Control Frames, Size Limits, Enums | 16 | **PASSED** |
| 5 | `test_p2p.py` | Direct Peer Endpoints, P2P Chat & Ack | Peer Sockets, Duplex Streaming, Sequence Order | 11 | **PASSED** |
| 6 | `test_file_transfer.py` | `FileChunkCodec.py`, `FileReq`, `FileDone` | Chunk Serialization, Reassembly, SHA-256 Hash | 12 | **PASSED** |
| **Total** | **6 Modules** | **Entire Application Stack** | **End-to-End Test Suite** | **72** | **100% OK** |

---

## 2. Test Execution Guide

### Prerequisites
- Python 3.10 or higher.
- Set `PYTHONPATH` to the project root directory so that modules (`common`, `daemon`, `client`, etc.) resolve cleanly.

### Running Commands

#### Run the Entire Test Suite:
```bash
# Windows PowerShell
$env:PYTHONPATH = "."
python -m unittest discover -s tests -v

# Linux / macOS
PYTHONPATH=. python3 -m unittest discover -s tests -v
```

#### Run Specific Modules:
```bash
python -m unittest tests.test_packet_codec -v
python -m unittest tests.test_tcp_connection -v
python -m unittest tests.test_http -v
python -m unittest tests.test_auth -v
python -m unittest tests.test_p2p -v
python -m unittest tests.test_file_transfer -v
```

---

## 3. Comprehensive Test Catalog

---

### Module 1: `tests.test_packet_codec`
**Target Components:** `common.PacketCodec`, `common.PacketHeader`, `common.ProtocolConstants`

| Test Case Name | Component Checked | Aspect / Requirement Under Test | Input / Setup | Expected Outcome |
|---|---|---|---|---|
| `test_encode_returns_bytes` | `PacketCodec.encode` | Data type compliance | Packet with `"hello"` payload | Returns a `bytes` instance |
| `test_encode_length_is_header_plus_payload` | `PacketCodec.encode` | Framing & sizing calculation | Packet with 4-byte payload | Output length equals `HEADER_SIZE` (24 bytes) + 4 = 28 bytes |
| `test_encode_zero_payload` | `PacketCodec.encode` | Zero-payload control frames | Packet with `b""` | Output length equals exactly `HEADER_SIZE` (24 bytes) |
| `test_encode_rejects_none` | `PacketCodec.encode` | Defensive input validation | `None` passed to `encode()` | Raises `ValueError` or `TypeError` |
| `test_encode_rejects_oversized_payload` | `PacketCodec.encode` | Buffer protection & MTU boundary | Payload exceeding `MAX_PACKET_SIZE` | Raises `ValueError` indicating packet exceeds maximum size |
| `test_encode_rejects_invalid_version` | `PacketCodec.encode` | Protocol version negotiation | PacketHeader with `version=99` | Raises `ValueError` rejecting unsupported protocol version |
| `test_encode_rejects_invalid_message_type` | `PacketCodec.encode` | Message identification check | PacketHeader with `message_type=99` | Raises `ValueError` rejecting undefined message type |
| `test_decode_returns_packet` | `PacketCodec.decode` | Deserialization return type | Valid wire bytes | Returns valid `Packet` instance |
| `test_decode_rejects_none` | `PacketCodec.decode` | Null input safety | `None` passed to `decode()` | Raises `ValueError` |
| `test_decode_rejects_too_short` | `PacketCodec.decode` | Incomplete header reception | Byte sequence of 23 bytes (< 24) | Raises `ValueError` on incomplete header |
| `test_decode_rejects_oversized` | `PacketCodec.decode` | Packet size overflow prevention | Wire byte sequence of 1201 bytes (> 1200) | Raises `ValueError` on oversized packet |
| `test_roundtrip_binary_payload` | `PacketCodec` | Binary transparency (0x00 - 0xFF) | 768 bytes of varied binary data | Exact payload matches after encode + decode cycle |
| `test_roundtrip_empty_payload` | `PacketCodec` | Header-only roundtrip | Packet with empty payload `b""` | Decoded payload equals `b""` |
| `test_roundtrip_preserves_message_type` | `PacketCodec` | Header metadata fidelity | `CHAT_MESSAGE` packet | Decoded `message_type` equals original |
| `test_roundtrip_all_valid_message_types` | `PacketCodec` | Comprehensive enum coverage | Packets for types `1` through `20` | All 20 message types roundtrip without error |

---

### Module 2: `tests.test_tcp_connection`
**Target Components:** Raw OS TCP Socket Layer, `socket` module

| Test Case Name | Component Checked | Aspect / Requirement Under Test | Input / Setup | Expected Outcome |
|---|---|---|---|---|
| `test_client_can_connect` | TCP 3-Way Handshake | Basic connectivity | Client connects to background TCP server | Connection established without timeout or error |
| `test_server_echoes_data` | TCP Duplex Data Flow | Stream transmission integrity | Client sends `b"hello network"` | Server echoes identical `b"hello network"` |
| `test_multiple_clients_in_sequence` | Server Concurrency Readiness | Port reuse & connection teardown | 3 sequential client connections sending messages | All 3 connections succeed and receive correct responses |
| `test_connect_to_closed_port_raises` | TCP Handshake Failure Handling | Client error resilience | Connect to an unbound local port | Raises `ConnectionRefusedError` immediately |
| `test_server_close_causes_client_recv_empty` | TCP FIN / Termination Signaling | EOF detection on socket close | Server calls `conn.close()` immediately | Client `recv()` returns empty bytes `b""` (standard EOF indicator) |
| `test_socketpair_data_transfer` | Socket Pairing Layer | IPC data transport | Pair `(a, b)`: write `b"ping"` to `a` | `b.recv()` receives `b"ping"` |
| `test_socketpair_close_causes_eof` | Socket Pairing Layer | Clean shutdown propagation | Close `a` side of socketpair | `b.recv()` returns `b""` |
| `test_socketpair_bidirectional` | Full-Duplex Socket Behavior | Simultaneous bidirectional exchange | `a -> b` request, `b -> a` response | Both sides receive expected payloads |

---

### Module 3: `tests.test_http`
**Target Components:** `start_proxy.py`, `daemon/proxy.py`, `config/proxy.conf`

| Test Case Name | Component Checked | Aspect / Requirement Under Test | Input / Setup | Expected Outcome |
|---|---|---|---|---|
| `test_config_file_exists` | Configuration Loading | File availability | Checks `config/proxy.conf` | Path exists on disk |
| `test_parse_returns_dict` | `start_proxy.parse_virtual_hosts` | Parser return structure | Passes `config/proxy.conf` | Returns a valid `dict` mapping hostnames to backends |
| `test_parse_has_entries` | `start_proxy.parse_virtual_hosts` | Route population | Reads real config file | Dict has at least 1 configured route |
| `test_each_route_has_policy` | `start_proxy.parse_virtual_hosts` | Routing policy assignment | Iterates over parsed routes | Each value is a `(backends, policy)` tuple |
| `test_single_backend_resolved` | `resolve_routing_policy` | Static backend forwarding | Route with single target `"127.0.0.1:9001"` | Returns `('127.0.0.1', '9001')` |
| `test_multi_backend_round_robin` | `resolve_routing_policy` | **Round-Robin Load Balancing** | Route with `["127.0.0.1:9002", "127.0.0.1:9003"]` | Successive calls alternate between ports 9002 and 9003 |
| `test_unknown_host_returns_empty_or_default` | `resolve_routing_policy` | Missing route safety | Host `"unknown.host"` | Gracefully returns default without throwing uncaught exceptions |
| `test_empty_backend_list_returns_empty` | `resolve_routing_policy` | Empty route handling | Route with `[]` backends | Returns `('', '')` signaling 404 condition |
| `test_missing_host_header_returns_400` | `handle_client` (Proxy Daemon) | HTTP/1.1 RFC Compliance | Request with no `Host:` header | Proxy responds with `400 Bad Request` |
| `test_unknown_host_returns_404` | `handle_client` (Proxy Daemon) | Reverse Proxy Error Response | Request for non-existent virtual host | Proxy responds with `404 Not Found` |

---

### Module 4: `tests.test_auth`
**Target Components:** `common.MessageType`, Authentication Packets & Payloads

| Test Case Name | Component Checked | Aspect / Requirement Under Test | Input / Setup | Expected Outcome |
|---|---|---|---|---|
| `test_login_request_message_type_is_valid` | `MessageType.isValidMessage` | Enum registration | `MessageType.LOGIN_REQUEST` (1) | Returns `True` |
| `test_login_response_message_type_is_valid` | `MessageType.isValidMessage` | Enum registration | `MessageType.LOGIN_RESPONSE` (2) | Returns `True` |
| `test_encode_login_request_succeeds` | `PacketCodec.encode` | Auth frame serialization | JSON login request payload | Correctly packs into binary frame |
| `test_roundtrip_login_request` | `PacketCodec` | Login roundtrip fidelity | `{"username":"bob","password":"..."}` | Decoded packet retains type 1 and payload |
| `test_roundtrip_login_response` | `PacketCodec` | Login response fidelity | `{"status":"ok","user_id":42}` | Decoded packet retains type 2 and payload |
| `test_signup_request_message_type_is_valid` | `MessageType.isValidMessage` | Enum registration | `MessageType.SIGNUP_REQUEST` (12) | Returns `True` |
| `test_signup_response_message_type_is_valid` | `MessageType.isValidMessage` | Enum registration | `MessageType.SIGNUP_RESPONSE` (13) | Returns `True` |
| `test_roundtrip_signup_request` | `PacketCodec` | Signup request serialization | New registration JSON | Decoded packet retains type 12 |
| `test_roundtrip_signup_response` | `PacketCodec` | Signup response serialization | `{"status":"created"}` | Decoded packet retains type 13 |
| `test_logout_request_message_type_is_valid` | `MessageType.isValidMessage` | Enum registration | `MessageType.LOGOUT_REQUEST` (19) | Returns `True` |
| `test_logout_response_message_type_is_valid` | `MessageType.isValidMessage` | Enum registration | `MessageType.LOGOUT_RESPONSE` (20) | Returns `True` |
| `test_roundtrip_logout_request` | `PacketCodec` | Session teardown message | Empty logout frame | Decoded packet retains type 19 |
| `test_roundtrip_logout_response` | `PacketCodec` | Session teardown ACK | `{"status":"ok"}` | Decoded packet retains type 20 |
| `test_auth_payload_does_not_exceed_max_size` | Size Guard | Buffer overflow prevention | Normal auth credentials | Total encoded size <= 1200 bytes |
| `test_oversized_auth_payload_is_rejected` | Security Boundary | DoS payload prevention | Large auth payload (> 1200 bytes) | Raises `ValueError` |
| `test_message_type_values_match_expected_constants` | Protocol Constants | Numerical enum stability | Checks constants against specification | Types 1, 2, 12, 13, 19, 20 match exact integer values |

---

### Module 5: `tests.test_p2p`
**Target Components:** `client.PeerEndpoint`, Direct Peer Streaming Protocol

| Test Case Name | Component Checked | Aspect / Requirement Under Test | Input / Setup | Expected Outcome |
|---|---|---|---|---|
| `test_valid_peer_endpoint_creation` | `PeerEndpoint` Model | P2P node representation | Valid user_id, name, TCP, UDP socket tuples | Creates frozen data class instance correctly |
| `test_reject_invalid_user_id` | `PeerEndpoint.__post_init__` | P2P identity boundary | IDs <= 0, > 0xFFFFFFFF, or non-int | Raises `ValueError` / `TypeError` |
| `test_reject_empty_or_non_string_username` | `PeerEndpoint.__post_init__` | Username validation | `""`, `None`, numbers | Raises `ValueError` / `TypeError` |
| `test_reject_invalid_tcp_address` | `PeerEndpoint._validate_address` | Transport address format | Port 0, port 70000, empty host, wrong tuple length | Raises `ValueError` |
| `test_reject_invalid_udp_address` | `PeerEndpoint._validate_address` | Transport address format | Port < 0 or invalid structure | Raises `ValueError` |
| `test_chat_message_roundtrip` | P2P Streaming | Direct chat packet transmission | UTF-8 direct chat payload | Header sender, receiver, sequence, and payload intact |
| `test_ack_packet_roundtrip` | P2P Transport Confirmation | Delivery acknowledgement | ACK payload with `ack_seq` | Packet retains type 4 and payload |
| `test_heartbeat_packet_roundtrip` | P2P Session Liveness | Peer keep-alive ping | Empty heartbeat frame | Packet retains type 5 |
| `test_presence_update_message_type` | Peer State Synchronization | Online/offline status broadcast | Status JSON with `online` flag | Packet retains type 18 |
| `test_peer_duplex_chat_and_ack` | Full P2P Interaction Cycle | **Simulated Peer A ↔ Peer B exchange** | Peer A sends chat; Peer B decodes and sends ACK | Both peers successfully process their respective packets |
| `test_peer_streaming_sequence_order` | Stream Ordering | In-order message delivery | Stream of 3 chunk packets | Receiver reads packets in strict sequence `1 -> 2 -> 3` |

---

### Module 6: `tests.test_file_transfer`
**Target Components:** `common.FileChunkCodec`, `FileReq`, `FileAccept`, `FileReject`, `FileDone`

| Test Case Name | Component Checked | Aspect / Requirement Under Test | Input / Setup | Expected Outcome |
|---|---|---|---|---|
| `test_file_req_valid` | `FileReq` Payload Model | File transfer handshake request | UUID, file name, size, total_chunks, SHA-256 hash | Initializes valid control payload |
| `test_file_req_rejects_invalid_file_id` | `FileReq` Validation | UUIDv4 format enforcement | Non-UUID string `"invalid-uuid"` | Raises `ValueError` |
| `test_file_accept_valid` | `FileAccept` Payload Model | File transfer acceptance handshake | Valid UUID | Initializes valid acceptance payload |
| `test_file_reject_valid` | `FileReject` Payload Model | Transfer refusal signaling | Error code 3001, message | Contains error code and description |
| `test_file_done_valid` | `FileDone` Payload Model | Transfer completion notification | Valid UUID | Holds completed file ID |
| `test_chunk_codec_roundtrip` | `FileChunkCodec` | Binary wire format (16-byte UUID + order + len) | File chunk with binary data | Decoded object matches original order, UUID, and data |
| `test_chunk_codec_max_size` | `FileChunkCodec` | MTU capacity verification | 1024-byte payload (`MAX_CHUNK_DATA_SIZE`) | Encodes and decodes successfully |
| `test_chunk_codec_rejects_oversized_payload` | `FileChunkCodec` | Overflow boundary protection | 1025-byte payload | Rejected with `ValueError` |
| `test_chunk_codec_rejects_truncated_metadata` | `FileChunkCodec` | Incomplete frame guard | Byte array < 24 bytes | Raises `ValueError` |
| `test_normal_chunking_and_reassembly` | End-to-End File Transfer | **Multi-chunk partitioning & rebuild** | 3500-byte file (4 chunks) | Reassembled file has identical content and SHA-256 hash |
| `test_out_of_order_chunks_reassemble_correctly` | Reliable Reassembly | **Handling network jitter / reordering** | Chunks delivered in reverse order | Sorted by `chunk_order` to produce verified intact file |
| `test_corrupted_chunk_fails_checksum_verification` | File Integrity & Security | **Bit-flip error detection** | Inverting 1 byte in chunk 2 | Rebuilt hash mismatches expected SHA-256 (detected corruption) |

---

## 4. Key Design Decisions

1. **Pure Standard Library**: All test cases use Python standard libraries (`unittest`, `socket`, `struct`, `hashlib`, `uuid`) without external third-party dependencies (e.g., pytest, requests), ensuring lightweight execution in any undergraduate or CI environment.
2. **Defensive Socket Management**: Every socket created during testing is governed by `with` context managers and explicit `settimeout(2.0)` guards to eliminate deadlocks or hung processes on Windows loopback adapters.
3. **Traceability**: Every test case directly verifies an aspect required by the Assignment 1 specification (RFC-compliant HTTP reverse proxy, binary framing, peer-to-peer duplex streaming, and chunked file transfer with checksum validation).

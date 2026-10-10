# Smart LAN File Sharing System (v2.0)

A decentralized, portable, peer-to-peer file and folder sharing system designed for college Computer Networks projects and lab environments. Built with Python 3, Flask, SQLite, framed TCP binary sockets, and UDP broadcast discovery.

---

## 🌟 Key Features

- **Decentralized Architecture**: No dedicated server or admin PC required; every machine acts as a full peer node.
- **Strict Zero-Pollution Portability**: 
  - Never pollutes the project directory.
  - Configuration, SQLite database, and partial chunks reside outside the repository in `%LOCALAPPDATA%\SmartLANFileShare` (Windows) or `~/.smart_lan_share`.
  - Received files land strictly in the user's chosen Downloads directory (`%USERPROFILE%\Downloads\LAN File Sharing`).
  - Senders stream files straight from source without copying or duplicating data.
- **Persistent Identity**:
  - Username is configured on first launch and saved locally; subsequent launches load directly without re-prompting.
  - PC hostname is auto-detected dynamically via `socket.gethostname()`.
  - Unique persistent Device ID (UUIDv4) is generated locally.
  - LAN-wide username uniqueness validation over UDP broadcast.
- **UDP LAN Discovery**:
  - Periodically broadcasts discovery beacons every 3 seconds on UDP port `50055`.
  - Displays real-time online/offline status dots (🟢 Online, ⚫ Offline with 10s heartbeat timeout).
  - Broadcasts graceful departure beacons (`GOODBYE`) on shutdown.
- **Framed TCP Chunked Streaming & Resume**:
  - Binary framing protocol over TCP port `50056`.
  - Large files streamed in chunks without loading entire files into memory.
  - Interrupted transfers automatically resume from the missing offset using `.partial/` manifests.
  - Full-file SHA-256 integrity verification before finalizing to the Downloads directory.
- **Multi-Recipient Distribution**:
  - Select one or multiple target PCs with `[SELECT ALL]`/`[CLEAR ALL]`.
  - Independent transfer threads per recipient.
- **Interactive Transfer Approval**:
  - Receivers receive an incoming request modal displaying sender username, hostname, item name, and size.
  - Explicit `[ACCEPT]` and `[REJECT]` control.
- **Full Folder Sharing**:
  - Recursively scans directory hierarchies and preserves nested subfolder structures.
  - Built-in directory traversal protection.
- **Main Research Feature: Smart Adaptive Transfer**:
  - Evaluates **Baseline Fixed TCP Transfer** (64 KB constant chunks) against **Proposed Adaptive Chunk Transfer** (AIMD dynamic scaling from 32 KB to 2 MB based on RTT, ACK latency, and congestion feedback).
  - Logs transfer metrics (throughput, peak speed, RTT, retries) for academic research analysis.
- **Bandwidth Management & Priority Scheduling**:
  - Prioritizes transfers (`HIGH`, `MEDIUM`, `LOW`) with fair-sharing allocation and optional bandwidth throttling.

---

## 📐 Network Protocol Specification

### 1. UDP Broadcast Beacon (`Port 50055`)
- **Announce**:
  ```json
  {
    "type": "ANNOUNCE",
    "device_id": "8f32c91b-6d2b-4fa8-b219-44c11b0e2718",
    "username": "Devraj",
    "hostname": "Desktop-SK2A",
    "ip": "192.168.1.10",
    "tcp_port": 50056,
    "app_version": "2.0.0"
  }
  ```
- **Collision Check**:
  ```json
  { "type": "NAME_CHECK", "requested_username": "Devraj", "from_device_id": "..." }
  ```
  Collision response:
  ```json
  { "type": "NAME_TAKEN", "device_id": "...", "taken_username": "Devraj" }
  ```

### 2. TCP Wire Framing (`Port 50056`)
Every TCP frame starts with an 8-byte prefix:
```
+-------------------+----------------------+------------------------+-------------------------+
| Magic (4 bytes)   | Header Len (4 bytes) | JSON Header (variable) | Binary Payload (bytes)  |
| b'SLFS'           | uint32 big-endian    | UTF-8 string           | Length specified in hdr |
+-------------------+----------------------+------------------------+-------------------------+
```

### 3. Transfer Handshake & Streaming Flow
1. **Sender -> Receiver**: `TRANSFER_REQUEST` (contains transfer ID, metadata, file list, SHA-256).
2. **Receiver -> Sender**: `TRANSFER_RESPONSE` (`accepted: true/false`, `resume_offset: int`).
3. **Sender -> Receiver**: Streamed `CHUNK` packets with chunk offset, file index, and payload.
4. **Receiver -> Sender**: `CHUNK_ACK` (`status: "OK"`).
5. **Sender -> Receiver**: `TRANSFER_COMPLETE`.
6. **Receiver -> Sender**: Verification result (`verified: true/false`).

---

## 💻 Installation & Multi-PC Lab Setup

### Prerequisites
- Python 3.10+ installed.
- All PCs connected to the same Local Area Network (Wi-Fi or Ethernet switch).

### Step 1: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 2: Run Application
On **PC 1** (e.g. Desktop-SK2A):
```bash
python run.py
```
- A browser tab will open at `http://localhost:5000`.
- Enter your username (e.g. `Devraj`) on the first-launch welcome screen.

On **PC 2** (e.g. Desktop-SK2B):
```bash
python run.py
```
- Enter your username (e.g. `Rohan`).
- Both PCs will automatically discover each other over UDP broadcast and appear in **AVAILABLE DEVICES**!

---

## 🧪 Automated Testing

Run the full automated test suite (including end-to-end loopback TCP streaming, resume verification, and multi-PC portability isolation):

```bash
python -m pytest
```

---

## 🔬 Research & Analytics

Visit the **Research & Metrics** tab in the web UI to inspect:
- **Baseline vs Adaptive Throughput comparison**.
- **AIMD dynamic chunk sizing timeline** under varying network latencies.
- **Packet retries and recovery time** during simulated network hiccups.

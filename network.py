"""
LAN multiplayer networking for Goat Society RTS.

TCP framing: 4-byte big-endian length prefix + UTF-8 JSON body.
UDP discovery: host broadcasts "GOAT|<seed>|<name>" on port 45678.
TCP connection on port 45679.
"""
import socket
import struct
import json
import threading
import queue
import time


UDP_PORT = 45678
TCP_PORT = 45679
BROADCAST_INTERVAL = 1.0   # seconds between UDP beacons


# ---------------------------------------------------------------------------
# Low-level framing helpers
# ---------------------------------------------------------------------------

def send_msg(sock, data: dict):
    """Send a dict as a framed JSON message over a TCP socket."""
    raw = json.dumps(data).encode('utf-8')
    header = struct.pack('>I', len(raw))
    try:
        sock.sendall(header + raw)
        return True
    except (OSError, BrokenPipeError, ConnectionResetError):
        return False


def recv_msg(sock) -> dict | None:
    """
    Block until a full framed message arrives, then return the parsed dict.
    Returns None on socket error / disconnect.
    """
    try:
        header = _recv_exactly(sock, 4)
        if header is None:
            return None
        length = struct.unpack('>I', header)[0]
        if length == 0 or length > 16 * 1024 * 1024:   # sanity cap: 16 MB
            return None
        body = _recv_exactly(sock, length)
        if body is None:
            return None
        return json.loads(body.decode('utf-8'))
    except (OSError, json.JSONDecodeError, struct.error):
        return None


def _recv_exactly(sock, n: int) -> bytes | None:
    """Read exactly n bytes from sock, or return None on disconnect/error."""
    buf = b''
    while len(buf) < n:
        try:
            chunk = sock.recv(n - len(buf))
        except OSError:
            return None
        if not chunk:
            return None
        buf += chunk
    return buf


# ---------------------------------------------------------------------------
# IP helpers
# ---------------------------------------------------------------------------

def get_local_ip() -> str:
    """Return the LAN IP address of this machine (best-effort)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return '127.0.0.1'


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def discover_hosts(timeout: float = 2.0) -> list:
    """
    Listen on UDP_PORT for GOAT beacon packets for `timeout` seconds.
    Returns list of (addr_str, seed_int, host_name_str).
    """
    results = []
    seen_addrs = set()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(('', UDP_PORT))
    except OSError:
        sock.close()
        return results

    sock.settimeout(0.2)
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        try:
            data, addr = sock.recvfrom(256)
            text = data.decode('utf-8', errors='ignore')
            if text.startswith('GOAT|'):
                parts = text.split('|')
                if len(parts) >= 3:
                    ip = addr[0]
                    if ip not in seen_addrs:
                        seen_addrs.add(ip)
                        try:
                            seed = int(parts[1])
                        except ValueError:
                            seed = 0
                        name = parts[2]
                        results.append((ip, seed, name))
        except socket.timeout:
            pass
        except OSError:
            break

    sock.close()
    return results


# ---------------------------------------------------------------------------
# HostSession
# ---------------------------------------------------------------------------

class HostSession:
    """
    Manages the server side of a multiplayer session.
    - Broadcasts UDP beacon while in lobby.
    - Listens on TCP for a single client.
    - After connection, recv loop runs in a daemon thread.
    - Commands from client are queued; caller polls with poll_commands().
    - State snapshots sent to client with send_state().
    """

    def __init__(self, seed: int, host_name: str):
        self._seed = seed
        self._host_name = host_name

        self._client_name: str = ''
        self._client_ready: bool = False
        self._connected: bool = False

        self._cmd_queue: queue.Queue = queue.Queue()
        self._client_sock: socket.socket | None = None

        # TCP server socket
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind(('', TCP_PORT))
        self._server_sock.listen(1)
        self._server_sock.setblocking(False)

        # Start UDP beacon thread
        self._beacon_running = True
        self._beacon_thread = threading.Thread(target=self._beacon_loop, daemon=True)
        self._beacon_thread.start()

    # ------------------------------------------------------------------ beacon
    def _beacon_loop(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        msg = f'GOAT|{self._seed}|{self._host_name}'.encode('utf-8')
        while self._beacon_running:
            try:
                sock.sendto(msg, ('<broadcast>', UDP_PORT))
            except OSError:
                try:
                    sock.sendto(msg, ('127.255.255.255', UDP_PORT))
                except OSError:
                    pass
            time.sleep(BROADCAST_INTERVAL)
        sock.close()

    def _stop_beacon(self):
        self._beacon_running = False

    # ----------------------------------------------------------------- accept
    def try_accept(self) -> bool:
        """
        Non-blocking: check if a client has connected.
        If so, read their READY message, store name, return True.
        Call once per frame from lobby loop.
        """
        if self._connected:
            return True
        try:
            conn, _addr = self._server_sock.accept()
            conn.setblocking(True)
            self._client_sock = conn
            # Read READY message (blocking, but fast in practice)
            conn.settimeout(5.0)
            msg = recv_msg(conn)
            conn.settimeout(None)
            if msg and msg.get('t') == 'ready':
                self._client_name = msg.get('name', 'Player 2')
                self._client_ready = True
                self._connected = True
                # Start recv thread
                t = threading.Thread(target=self._recv_loop, daemon=True)
                t.start()
                return True
            else:
                conn.close()
                self._client_sock = None
        except BlockingIOError:
            pass
        except OSError:
            pass
        return False

    # ---------------------------------------------------------------- recv loop
    def _recv_loop(self):
        """Background thread: read commands from client and enqueue them."""
        sock = self._client_sock
        while self._connected and sock:
            msg = recv_msg(sock)
            if msg is None:
                self._connected = False
                break
            self._cmd_queue.put(msg)

    # ---------------------------------------------------------------- properties
    @property
    def client_name(self) -> str:
        return self._client_name

    def client_ready(self) -> bool:
        return self._client_ready

    def is_connected(self) -> bool:
        return self._connected

    # ----------------------------------------------------------------- send
    def send_start(self, client_team: int = 1):
        """Send the START packet and stop the UDP beacon."""
        self._stop_beacon()
        if self._client_sock:
            send_msg(self._client_sock, {
                't': 'start',
                'seed': self._seed,
                'client_team': client_team,
            })

    def send_state(self, state_dict: dict):
        """Send a state snapshot to the client."""
        if self._connected and self._client_sock:
            ok = send_msg(self._client_sock, state_dict)
            if not ok:
                self._connected = False

    # ----------------------------------------------------------------- poll
    def poll_commands(self) -> list:
        """Return all pending command dicts received from the client."""
        cmds = []
        while True:
            try:
                cmds.append(self._cmd_queue.get_nowait())
            except queue.Empty:
                break
        return cmds

    # ----------------------------------------------------------------- close
    def close(self):
        self._stop_beacon()
        self._connected = False
        if self._client_sock:
            try:
                self._client_sock.close()
            except OSError:
                pass
            self._client_sock = None
        try:
            self._server_sock.close()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# ClientSession
# ---------------------------------------------------------------------------

class ClientSession:
    """
    Manages the client side of a multiplayer session.
    - Connects to a host over TCP.
    - Recv loop runs in a daemon thread.
    - State snapshots are kept; only the latest is returned by poll_state()
      (older ones are discarded to prevent lag accumulation).
    - Commands sent to host with send_command().
    """

    def __init__(self):
        self._sock: socket.socket | None = None
        self._connected: bool = False

        self._state_queue: queue.Queue = queue.Queue()
        self._latest_state: dict | None = None

        self.start_info: dict | None = None   # set when 'start' msg received

    def connect(self, host_addr: str):
        """Connect to host at host_addr:TCP_PORT. Raises on failure."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.connect((host_addr, TCP_PORT))
        sock.settimeout(None)
        self._sock = sock
        self._connected = True
        # Start recv thread
        t = threading.Thread(target=self._recv_loop, daemon=True)
        t.start()

    # ---------------------------------------------------------------- recv loop
    def _recv_loop(self):
        sock = self._sock
        while self._connected and sock:
            msg = recv_msg(sock)
            if msg is None:
                self._connected = False
                break
            t = msg.get('t')
            if t == 'start':
                self.start_info = msg
            elif t == 'state':
                # Keep draining; only the newest matters
                self._state_queue.put(msg)
            # Other message types can be ignored or extended later

    # ---------------------------------------------------------------- send
    def send_ready(self, name: str):
        """Send the READY packet with our player name."""
        if self._sock:
            send_msg(self._sock, {'t': 'ready', 'name': name})

    def send_command(self, data: dict):
        """Send a command dict to the host."""
        if self._connected and self._sock:
            ok = send_msg(self._sock, data)
            if not ok:
                self._connected = False

    # ---------------------------------------------------------------- poll
    def poll_state(self) -> dict | None:
        """
        Drain the state queue and return the *latest* state dict, or None
        if no new state has arrived since last call.
        Older frames are discarded to prevent the client from lagging behind.
        """
        latest = None
        while True:
            try:
                latest = self._state_queue.get_nowait()
            except queue.Empty:
                break
        return latest

    # ---------------------------------------------------------------- properties
    def is_connected(self) -> bool:
        return self._connected

    # ----------------------------------------------------------------- close
    def close(self):
        self._connected = False
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

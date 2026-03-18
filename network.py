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
    Returns list of (addr_str, seed_int, host_name_str, players_int, max_players_int).
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
                        # Parse player count if available
                        try:
                            n_clients = int(parts[3]) if len(parts) > 3 else 0
                            max_clients = int(parts[4]) if len(parts) > 4 else 5
                        except ValueError:
                            n_clients, max_clients = 0, 5
                        # +1 for host in both counts
                        results.append((ip, seed, name, n_clients + 1, max_clients + 1))
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
    - Listens on TCP for up to (max_players - 1) clients.
    - After connection, recv loop runs in a daemon thread per client.
    - Commands from all clients are queued; caller polls with poll_commands().
    - State snapshots broadcast to all connected clients with send_state().
    """

    def __init__(self, seed: int, host_name: str, max_clients: int = 5):
        self._seed = seed
        self._host_name = host_name
        self._max_clients = max_clients

        # Each client entry: {sock, name, team, connected, thread}
        self._clients: list[dict] = []
        self._clients_lock = threading.Lock()

        self._cmd_queue: queue.Queue = queue.Queue()

        # TCP server socket
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind(('', TCP_PORT))
        self._server_sock.listen(5)
        self._server_sock.setblocking(False)

        # Start UDP beacon thread
        self._beacon_running = True
        self._beacon_thread = threading.Thread(target=self._beacon_loop, daemon=True)
        self._beacon_thread.start()

    # ------------------------------------------------------------------ beacon
    def _beacon_loop(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        while self._beacon_running:
            n = len(self._clients)
            msg = f'GOAT|{self._seed}|{self._host_name}|{n}|{self._max_clients}'.encode('utf-8')
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
        Non-blocking: check if a new client has connected.
        Accepts multiple clients up to max_clients.
        Returns True if a new client was accepted this call.
        Call once per frame from lobby loop.
        """
        if len(self._clients) >= self._max_clients:
            return False
        try:
            conn, _addr = self._server_sock.accept()
            conn.setblocking(True)
            # Read READY message (blocking, but fast in practice)
            conn.settimeout(5.0)
            msg = recv_msg(conn)
            conn.settimeout(None)
            if msg and msg.get('t') == 'ready':
                # Assign next available team (host is team 0, clients get 1, 2, 3...)
                team = len(self._clients) + 1
                client = {
                    'sock': conn,
                    'name': msg.get('name', f'Player {team + 1}'),
                    'team': team,
                    'connected': True,
                }
                # Start recv thread for this client
                t = threading.Thread(target=self._recv_loop,
                                     args=(client,), daemon=True)
                client['thread'] = t
                with self._clients_lock:
                    self._clients.append(client)
                t.start()
                return True
            else:
                conn.close()
        except BlockingIOError:
            pass
        except OSError:
            pass
        return False

    # ---------------------------------------------------------------- recv loop
    def _recv_loop(self, client: dict):
        """Background thread: read commands from one client and enqueue them."""
        sock = client['sock']
        while client['connected']:
            msg = recv_msg(sock)
            if msg is None:
                client['connected'] = False
                break
            self._cmd_queue.put(msg)

    # ---------------------------------------------------------------- properties
    @property
    def client_names(self) -> list[str]:
        """Return list of connected client names."""
        with self._clients_lock:
            return [c['name'] for c in self._clients if c['connected']]

    @property
    def num_clients(self) -> int:
        with self._clients_lock:
            return sum(1 for c in self._clients if c['connected'])

    @property
    def clients_info(self) -> list[dict]:
        """Return list of {name, team, connected} for each client."""
        with self._clients_lock:
            return [{'name': c['name'], 'team': c['team'],
                     'connected': c['connected']} for c in self._clients]

    # Backwards compat: single-client property
    @property
    def client_name(self) -> str:
        names = self.client_names
        return names[0] if names else ''

    def is_connected(self) -> bool:
        """True if at least one client is still connected."""
        with self._clients_lock:
            return any(c['connected'] for c in self._clients)

    # ----------------------------------------------------------------- send
    def send_start(self, config=None):
        """Send the START packet to all clients and stop the UDP beacon."""
        self._stop_beacon()
        with self._clients_lock:
            for c in self._clients:
                if c['connected']:
                    send_msg(c['sock'], {
                        't': 'start',
                        'seed': self._seed,
                        'client_team': c['team'],
                        'config': config or {},
                    })

    def send_state(self, state_dict: dict):
        """Broadcast a state snapshot to all connected clients."""
        # Pre-encode once, send to all
        raw = json.dumps(state_dict).encode('utf-8')
        header = struct.pack('>I', len(raw))
        frame = header + raw
        with self._clients_lock:
            for c in self._clients:
                if c['connected']:
                    try:
                        c['sock'].sendall(frame)
                    except (OSError, BrokenPipeError, ConnectionResetError):
                        c['connected'] = False

    # ----------------------------------------------------------------- poll
    def poll_commands(self) -> list:
        """Return all pending command dicts received from all clients."""
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
        with self._clients_lock:
            for c in self._clients:
                c['connected'] = False
                try:
                    c['sock'].close()
                except OSError:
                    pass
            self._clients.clear()
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

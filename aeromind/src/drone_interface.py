import socket
import threading
import time


class DroneInterface:
    """
    Real DJI Tello Drone Interface (SDK 2.0)

    - Command channel: UDP 8889
    - State channel:   UDP 8890
    """

    TELLO_IP = "192.168.10.1"
    CMD_PORT = 8889
    STATE_PORT = 8890
    TIMEOUT = 5.0

    def __init__(self, enabled: bool = False):
        self.enabled = enabled
        self.cmd_sock = None
        self.state_sock = None
        self.state = {
            "battery_pct": None,
            "height_cm": None
        }
        self._running = False

    # =========================
    # CONNECT
    # =========================
    def connect(self) -> bool:
        if not self.enabled:
            print("[Drone] SIM mode")
            return True

        try:
            print("[Drone] Connecting to Tello...")

            # Command socket
            self.cmd_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.cmd_sock.settimeout(self.TIMEOUT)

            # State socket
            self.state_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.state_sock.bind(("", self.STATE_PORT))

            # Enter SDK mode
            self._send_cmd("command")

            # Start telemetry thread
            self._running = True
            threading.Thread(target=self._state_loop, daemon=True).start()

            print("[Drone] Connected (SDK mode)")
            return True

        except Exception as e:
            print(f"[Drone] Connection failed: {e}")
            self.enabled = False
            return False

    # =========================
    # SEND COMMAND
    # =========================
    def send_command(self, cmd: str) -> bool:
        if not self.enabled:
            return True

        try:
            self._send_cmd(cmd)
            return True
        except Exception as e:
            print(f"[Drone] Command failed ({cmd}): {e}")
            return False

    # =========================
    # TELEMETRY
    # =========================
    def poll_state(self):
        return self.state

    def _state_loop(self):
        while self._running:
            try:
                data, _ = self.state_sock.recvfrom(1024)
                self._parse_state(data.decode("utf-8"))
            except:
                pass

    def _parse_state(self, msg: str):
        """
        Example:
        bat:87;h:0;tof:10;...
        """
        parts = msg.strip().split(";")
        for p in parts:
            if ":" not in p:
                continue
            k, v = p.split(":")
            if k == "bat":
                self.state["battery_pct"] = int(v)
            if k == "h":
                self.state["height_cm"] = int(v)

    # =========================
    # LOW-LEVEL SEND
    # =========================
    def _send_cmd(self, cmd: str):
        self.cmd_sock.sendto(cmd.encode("utf-8"), (self.TELLO_IP, self.CMD_PORT))
        resp, _ = self.cmd_sock.recvfrom(1024)
        resp = resp.decode("utf-8").strip()
        if resp != "ok":
            raise RuntimeError(f"Tello error: {resp}")

    # =========================
    # CLEANUP
    # =========================
    def close(self):
        self._running = False
        if self.cmd_sock:
            self.cmd_sock.close()
        if self.state_sock:
            self.state_sock.close()

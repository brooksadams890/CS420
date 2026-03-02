import cv2
import time


class TelloVideoSource:
    """
    OpenCV reader for Tello UDP video 11111
    lifecycle:
      video = TelloVideoSource(drone)
      video.start()  # after drone.connect()
      ok, frame = video.read()
      video.release()
    """

    def __init__(self, drone_interface, *, warmup_s: float = 0.8):
        self.drone = drone_interface
        self.warmup_s = warmup_s
        self.cap = None
        self._started = False

    def start(self) -> bool:
        if self._started:
            return True

        if not getattr(self.drone, "enabled", False) or not getattr(self.drone, "cmd_sock", None):
            print("[Video] Drone not connected yet")
            return False

        # start clean
        try:
            self.drone.send_command("streamoff")
        except:
            pass
        if not self.drone.send_command("streamon"):
            print("[Video] streamon failed")
            return False

        self.cap = cv2.VideoCapture("udp://0.0.0.0:11111", cv2.CAP_FFMPEG)
        time.sleep(self.warmup_s)

        # quick sanity check read a few frames
        for _ in range(20):
            ok, frame = self.cap.read()
            if ok and frame is not None:
                self._started = True
                print("[Video] Tello stream ready")
                return True
            time.sleep(0.05)

        print("[Video] No frames from Tello stream")
        return False

    def read(self):
        if not self.cap:
            return False, None
        return self.cap.read()

    def release(self):
        if self.cap:
            try:
                self.cap.release()
            except:
                pass
            self.cap = None

        if self._started and getattr(self.drone, "enabled", False):
            try:
                self.drone.send_command("streamoff")
            except:
                pass
        self._started = False
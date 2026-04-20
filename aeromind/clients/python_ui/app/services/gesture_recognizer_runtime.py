from __future__ import annotations

from pathlib import Path
import sys
from threading import Condition
from time import monotonic
from typing import Any

from app.config import AppConfig
from app.gestures.gesture_tilt_extractor import extract_point_up_tilt
import math
from app.gestures.registry import SUPPORTED_GESTURES, get_gesture_definition_by_recognizer_label
from app.gestures.types import DetectorStatus, RawGestureSample
from app.utils.logging_utils import gesture_debug_log


def _format_exception(exc: Exception | None) -> str | None:
    if exc is None:
        return None
    return f"{type(exc).__name__}: {exc}"


_MEDIAPIPE_IMPORT_ERROR: Exception | None = None

try:
    import mediapipe as mp
except Exception as exc:  # pragma: no cover - optional dependency
    mp = None
    _MEDIAPIPE_IMPORT_ERROR = exc

gesture_debug_log(
    "inference.mediapipe_import",
    success=_MEDIAPIPE_IMPORT_ERROR is None,
    error=_format_exception(_MEDIAPIPE_IMPORT_ERROR),
)


def _distance(a: Any, b: Any) -> float:
    ax = float(getattr(a, "x", 0.0))
    ay = float(getattr(a, "y", 0.0))
    bx = float(getattr(b, "x", 0.0))
    by = float(getattr(b, "y", 0.0))
    return math.hypot(ax - bx, ay - by)


def _is_finger_extended(tip: Any, pip: Any) -> bool:
    return float(getattr(tip, "y", 1.0)) < float(getattr(pip, "y", 1.0))


def _is_finger_curled(tip: Any, pip: Any, *, margin: float = 0.015) -> bool:
    return float(getattr(tip, "y", 0.0)) >= (float(getattr(pip, "y", 0.0)) - margin)


def _extract_landmarks(result: Any) -> list[Any] | None:
    hand_landmarks = getattr(result, "hand_landmarks", None)
    if not hand_landmarks or not hand_landmarks[0] or len(hand_landmarks[0]) < 21:
        return None
    return hand_landmarks[0]


def _detect_pointing_left_right(result: Any) -> str | None:
    landmarks = _extract_landmarks(result)
    if landmarks is None:
        return None
    wrist = landmarks[0]
    index_mcp = landmarks[5]
    middle_pip = landmarks[10]
    ring_pip = landmarks[14]
    pinky_pip = landmarks[18]
    index_tip = landmarks[8]
    index_pip = landmarks[6]
    middle_tip = landmarks[12]
    ring_tip = landmarks[16]
    pinky_tip = landmarks[20]

    palm_scale = max(_distance(wrist, index_mcp), 1e-6)
    dx = float(getattr(index_tip, "x", 0.0)) - float(getattr(index_mcp, "x", 0.0))
    dy = float(getattr(index_tip, "y", 0.0)) - float(getattr(index_mcp, "y", 0.0))

    index_extended = _is_finger_extended(index_tip, index_pip)
    middle_curled = _is_finger_curled(middle_tip, middle_pip)
    ring_curled = _is_finger_curled(ring_tip, ring_pip)
    pinky_curled = _is_finger_curled(pinky_tip, pinky_pip)

    if not (index_extended and middle_curled and ring_curled and pinky_curled):
        return None
    if abs(dx) < palm_scale * 0.55:
        return None
    if abs(dx) <= abs(dy) * 1.15:
        return None
    return "point_right" if dx > 0 else "point_left"


def _detect_middle_finger_sign(result: Any) -> bool:
    landmarks = _extract_landmarks(result)
    if landmarks is None:
        return False
    wrist = landmarks[0]
    middle_mcp = landmarks[9]
    index_tip = landmarks[8]
    index_pip = landmarks[6]
    middle_tip = landmarks[12]
    middle_pip = landmarks[10]
    ring_tip = landmarks[16]
    ring_pip = landmarks[14]
    pinky_tip = landmarks[20]
    pinky_pip = landmarks[18]

    palm_scale = max(_distance(wrist, middle_mcp), 1e-6)
    middle_extended = _is_finger_extended(middle_tip, middle_pip)
    index_curled = _is_finger_curled(index_tip, index_pip)
    ring_curled = _is_finger_curled(ring_tip, ring_pip)
    pinky_curled = _is_finger_curled(pinky_tip, pinky_pip)
    extension = float(getattr(middle_pip, "y", 1.0)) - float(getattr(middle_tip, "y", 1.0))
    return bool(middle_extended and index_curled and ring_curled and pinky_curled and extension >= palm_scale * 0.45)


def _detect_spock_sign(result: Any) -> bool:
    hand_landmarks = getattr(result, "hand_landmarks", None)
    if not hand_landmarks or not hand_landmarks[0] or len(hand_landmarks[0]) < 21:
        return False
    landmarks = hand_landmarks[0]
    wrist = landmarks[0]
    index_mcp = landmarks[5]
    middle_mcp = landmarks[9]
    ring_mcp = landmarks[13]
    pinky_mcp = landmarks[17]
    thumb_tip = landmarks[4]
    thumb_ip = landmarks[3]
    index_tip = landmarks[8]
    index_pip = landmarks[6]
    middle_tip = landmarks[12]
    middle_pip = landmarks[10]
    ring_tip = landmarks[16]
    ring_pip = landmarks[14]
    pinky_tip = landmarks[20]
    pinky_pip = landmarks[18]

    palm_scale = max(_distance(wrist, middle_mcp), _distance(index_mcp, pinky_mcp), 1e-6)
    index_extended = _is_finger_extended(index_tip, index_pip)
    middle_extended = _is_finger_extended(middle_tip, middle_pip)
    ring_extended = _is_finger_extended(ring_tip, ring_pip)
    pinky_extended = _is_finger_extended(pinky_tip, pinky_pip)
    thumb_extended = _distance(thumb_tip, thumb_ip) > palm_scale * 0.12

    gap_index_middle = _distance(index_tip, middle_tip)
    gap_middle_ring = _distance(middle_tip, ring_tip)
    gap_ring_pinky = _distance(ring_tip, pinky_tip)

    return bool(
        thumb_extended
        and index_extended
        and middle_extended
        and ring_extended
        and pinky_extended
        and gap_middle_ring >= palm_scale * 0.40
        and gap_index_middle <= palm_scale * 0.34
        and gap_ring_pinky <= palm_scale * 0.34
    )

def _detect_ok_sign(result: Any) -> bool:
    hand_landmarks = getattr(result, "hand_landmarks", None)
    if not hand_landmarks or not hand_landmarks[0] or len(hand_landmarks[0]) < 21:
        return False
    landmarks = hand_landmarks[0]
    thumb_tip = landmarks[4]
    index_tip = landmarks[8]
    wrist = landmarks[0]
    index_mcp = landmarks[5]
    pinky_mcp = landmarks[17]
    middle_tip = landmarks[12]
    middle_pip = landmarks[10]
    ring_tip = landmarks[16]
    ring_pip = landmarks[14]
    pinky_tip = landmarks[20]
    pinky_pip = landmarks[18]

    palm_scale = max(_distance(wrist, index_mcp), _distance(wrist, pinky_mcp), 1e-6)
    thumb_index_distance = _distance(thumb_tip, index_tip)
    middle_extended = _is_finger_extended(middle_tip, middle_pip)
    ring_extended = _is_finger_extended(ring_tip, ring_pip)
    pinky_extended = _is_finger_extended(pinky_tip, pinky_pip)
    return thumb_index_distance <= palm_scale * 0.42 and middle_extended and ring_extended and pinky_extended


class GestureRecognizerRuntime:
    _RECOGNIZER_RESULT_TIMEOUT_S = 0.25

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self.max_num_hands = max(1, int(self._config.gesture_inference.max_num_hands))
        self._detector: Any | None = None
        self._recognizer: Any | None = None
        self._detector_available = False
        self._detector_status: DetectorStatus = "detector_unavailable"
        self._detector_error: str | None = None
        self._model_path = self._resolve_model_path()
        self._init_attempted = False
        self._detector_unavailable_logged = False
        self._recognition_condition = Condition()
        self._pending_recognition: dict[int, RawGestureSample] = {}
        self._last_timestamp_ms = 0

    @property
    def detector(self) -> Any | None:
        return self._detector

    @property
    def detector_available(self) -> bool:
        return self._detector_available

    @property
    def detector_status(self) -> DetectorStatus:
        return self._detector_status

    @property
    def detector_error(self) -> str | None:
        return self._detector_error

    @property
    def model_path(self) -> str | None:
        return self._model_path

    def ensure_initialized(self, *, reason: str) -> bool:
        if self._init_attempted:
            return self._detector_available
        self._init_attempted = True
        self._initialize_detector(reason=reason)
        return self._detector_available

    def log_detector_unavailable_once(self, *, frame_shape: Any, frame_dtype: Any) -> None:
        if self._detector_unavailable_logged:
            return
        self._detector_unavailable_logged = True
        gesture_debug_log(
            "inference.detector_unavailable",
            frame_shape=frame_shape,
            frame_dtype=frame_dtype,
            detector_available=self._detector_available,
            detector_status=self._detector_status,
            model_path=self._model_path,
            error=self._detector_error,
            queue_state=self._detector_status,
        )

    def recognize_rgb_frame(self, rgb_frame: Any) -> RawGestureSample:
        if mp is None or self._recognizer is None:
            raise RuntimeError("Gesture recognizer runtime is unavailable")

        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        timestamp_ms = self._next_timestamp_ms()
        with self._recognition_condition:
            self._pending_recognition.pop(timestamp_ms, None)
        self._recognizer.recognize_async(mp_image, timestamp_ms)
        return self._await_recognition_result(timestamp_ms)

    def _initialize_detector(self, *, reason: str) -> None:
        gesture_debug_log(
            "inference.detector_init_start",
            reason=reason,
            python=sys.executable,
            mediapipe_imported=mp is not None,
            mediapipe_version=getattr(mp, "__version__", None),
            model_path=self._model_path,
        )

        if mp is None:
            self._set_detector_failure(
                status="detector_missing_dependency",
                error=_format_exception(_MEDIAPIPE_IMPORT_ERROR) or "MediaPipe import failed",
                dependencies_available=False,
            )
            return

        try:
            from mediapipe.tasks import python
            from mediapipe.tasks.python import vision
        except Exception as exc:
            self._set_detector_failure(
                status="detector_missing_dependency",
                error=_format_exception(exc) or "MediaPipe Tasks API import failed",
                dependencies_available=False,
            )
            return

        if self._model_path is None:
            self._set_detector_failure(
                status="detector_init_failed",
                error="Gesture detector model path could not be resolved",
                dependencies_available=True,
            )
            return

        model_path = Path(self._model_path)
        if not model_path.is_file():
            self._set_detector_failure(
                status="detector_init_failed",
                error=f"Model file not found: {model_path}",
                dependencies_available=True,
            )
            return

        try:
            options = vision.GestureRecognizerOptions(
                base_options=python.BaseOptions(model_asset_path=str(model_path)),
                running_mode=vision.RunningMode.LIVE_STREAM,
                num_hands=self.max_num_hands,
                result_callback=self._on_recognition_result,
            )
            self._recognizer = vision.GestureRecognizer.create_from_options(options)
            self._detector = self._recognizer
            self._detector_available = True
            self._detector_status = "detector_ready"
            self._detector_error = None
            gesture_debug_log(
                "inference.detector_init_success",
                detector_available=self._detector_available,
                detector_status=self._detector_status,
                recognition_source="recognizer",
                dependencies_available=True,
                model_path=self._model_path,
                detector_type="GestureRecognizer",
            )
        except Exception as exc:
            self._set_detector_failure(
                status="detector_init_failed",
                error=_format_exception(exc) or "GestureRecognizer creation failed",
                dependencies_available=True,
            )

    def _set_detector_failure(
        self,
        *,
        status: DetectorStatus,
        error: str,
        dependencies_available: bool,
    ) -> None:
        self._detector = None
        self._detector_available = False
        self._detector_status = status
        self._detector_error = error
        gesture_debug_log(
            "inference.detector_init_failure",
            detector_available=self._detector_available,
            detector_status=self._detector_status,
            dependencies_available=dependencies_available,
            model_path=self._model_path,
            error=error,
        )

    def _resolve_model_path(self) -> str:
        project_root = Path(__file__).resolve().parents[4]
        return str(project_root / "models" / "gesture_recognizer.task")

    def _next_timestamp_ms(self) -> int:
        timestamp_ms = int(monotonic() * 1000.0)
        if timestamp_ms <= self._last_timestamp_ms:
            timestamp_ms = self._last_timestamp_ms + 1
        self._last_timestamp_ms = timestamp_ms
        return timestamp_ms

    def _await_recognition_result(self, timestamp_ms: int) -> RawGestureSample:
        deadline = monotonic() + self._RECOGNIZER_RESULT_TIMEOUT_S
        with self._recognition_condition:
            while timestamp_ms not in self._pending_recognition:
                remaining = deadline - monotonic()
                if remaining <= 0.0:
                    gesture_debug_log(
                        "inference.recognizer_timeout",
                        timestamp_ms=timestamp_ms,
                        timeout_s=self._RECOGNIZER_RESULT_TIMEOUT_S,
                        detector_available=self._detector_available,
                        detector_status=self._detector_status,
                    )
                    return RawGestureSample(
                        recognizer_label=None,
                        mapped_gesture=None,
                        confidence=None,
                        tilt_value=None,
                        raw_direction=None,
                        index_mcp_x=None,
                        index_tip_x=None,
                    )
                self._recognition_condition.wait(timeout=remaining)
            return self._pending_recognition.pop(timestamp_ms)

    def _on_recognition_result(self, result: Any, output_image: Any, timestamp_ms: int) -> None:
        recognizer_label: str | None = None
        gesture_name: str | None = None
        confidence: float | None = None
        tilt_value: float | None = None
        raw_direction: str | None = None
        index_mcp_x: float | None = None
        index_tip_x: float | None = None
        try:
            gestures = getattr(result, "gestures", None)
            if gestures and len(gestures) > 0 and gestures[0]:
                top = gestures[0][0]
                recognizer_label = getattr(top, "category_name", None)
                gesture_name = self._map_recognizer_label(recognizer_label)
                score = getattr(top, "score", None)
                confidence = float(score) if score is not None else None
            explicit_direction = _detect_pointing_left_right(result)
            if _detect_spock_sign(result):
                recognizer_label = "SPOCK_SIGN"
                gesture_name = "spock"
                confidence = max(float(confidence or 0.0), 0.96)
            elif _detect_ok_sign(result):
                recognizer_label = recognizer_label or "OK_SIGN"
                gesture_name = "ok_sign"
                confidence = max(float(confidence or 0.0), 0.93)
            elif _detect_middle_finger_sign(result):
                recognizer_label = "MIDDLE_FINGER"
                gesture_name = "middle_finger"
                confidence = max(float(confidence or 0.0), 0.96)
            elif explicit_direction is not None:
                recognizer_label = recognizer_label or explicit_direction.upper()
                gesture_name = explicit_direction
                confidence = max(float(confidence or 0.0), 0.91)
            if gesture_name == "point_up":
                tilt_value, raw_direction, index_mcp_x, index_tip_x = extract_point_up_tilt(result)
        except Exception as exc:
            gesture_debug_log(
                "inference.recognizer_callback_error",
                timestamp_ms=timestamp_ms,
                error=_format_exception(exc),
            )
            gesture_name = None
            confidence = None

        gesture_debug_log(
            "inference.recognizer_result",
            timestamp_ms=timestamp_ms,
            recognition_source="recognizer",
            recognizer_label=recognizer_label,
            mapped_gesture=gesture_name,
            raw_gesture=gesture_name,
            confidence=confidence,
            tilt_value=tilt_value,
            raw_direction=raw_direction,
            index_mcp_x=index_mcp_x,
            index_tip_x=index_tip_x,
        )
        with self._recognition_condition:
            self._pending_recognition[timestamp_ms] = RawGestureSample(
                recognizer_label=recognizer_label,
                mapped_gesture=gesture_name,
                confidence=confidence,
                tilt_value=tilt_value,
                raw_direction=raw_direction,
                index_mcp_x=index_mcp_x,
                index_tip_x=index_tip_x,
            )
            self._recognition_condition.notify_all()

    @staticmethod
    def _map_recognizer_label(label: str | None) -> str | None:
        gesture = get_gesture_definition_by_recognizer_label(label)
        if gesture is None:
            return None
        if gesture.internal_name not in SUPPORTED_GESTURES:
            return None
        return gesture.internal_name

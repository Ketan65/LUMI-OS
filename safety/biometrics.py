"""Biometric-Guard — Webcam Gaze, Physical Presence Sentry & Anti-Shoulder-Surfing (Phase 13).

Features:
  1. FaceProfileManager: Enrolls & matches master face vectors using OpenCV SFace 128D embeddings.
  2. PrivacyShield: Minimizes sensitive windows (VS Code, terminal, banking, wallets) on unauthorized shoulder-surfing.
  3. PresenceWatcher: Zero-latency 1 FPS physical presence radar that tracks away-time, auto-locks workstation,
     and emits 'Welcome back, Boss' notifications upon return.
"""

from __future__ import annotations

import base64
import ctypes
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None

try:
    import win32con
    import win32gui
except ImportError:
    win32gui = None
    win32con = None

logger = logging.getLogger("lumi.biometrics")

# Default sensitive keywords to shield when shoulder-surfer detected
DEFAULT_SHIELD_KEYWORDS = [
    "visual studio code", "vscode", "pycharm", "cursor", "sublime",
    "telegram", "discord", "slack", "signal", "whatsapp",
    "chrome", "edge", "firefox", "brave",
    "password", "bitwarden", "1password", "keepass",
    "wallet", "metamask", "binance", "banking", "zerodha",
    "terminal", "powershell", "cmd", "bash", "git bash", "mintty"
]


class FaceProfileManager:
    """Manages enrolled biometric face embeddings locally and performs cosine verification."""

    def __init__(self, data_path: str | Path = "data/biometrics.json",
                 model_path: str | Path = "data/face_recognition_sface.onnx") -> None:
        self.data_path = Path(data_path)
        self.model_path = Path(model_path)
        self._profiles: dict[str, dict] = {}
        self._recognizer = None
        self._init_recognizer()
        self.load()

    def _init_recognizer(self) -> None:
        if cv2 is not None and hasattr(cv2, "FaceRecognizerSF") and self.model_path.exists():
            try:
                self._recognizer = cv2.FaceRecognizerSF.create(str(self.model_path), "")
            except Exception as e:
                logger.warning("Could not initialize SFace recognizer: %s", e)
                self._recognizer = None

    def load(self) -> None:
        if self.data_path.exists():
            try:
                with open(self.data_path, "r", encoding="utf-8") as f:
                    self._profiles = json.load(f)
            except Exception as e:
                logger.error("Failed to load biometrics profiles: %s", e)
                self._profiles = {}

    def save(self) -> None:
        self.data_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.data_path, "w", encoding="utf-8") as f:
            json.dump(self._profiles, f, indent=2)

    def extract_features(self, face_img: np.ndarray, face_box_or_landmarks: Any = None) -> np.ndarray | None:
        """Extracts 128D feature embedding vector from aligned face image."""
        if face_img is None or face_img.size == 0:
            return None

        if self._recognizer is not None and face_box_or_landmarks is not None:
            try:
                # SFace alignCrop + feature
                aligned = self._recognizer.alignCrop(face_img, face_box_or_landmarks)
                feat = self._recognizer.feature(aligned)
                return np.asarray(feat).flatten()
            except Exception as e:
                logger.debug("SFace extraction fallback: %s", e)

        # Fallback normalized spatial color-histogram embedding (128D)
        try:
            resized = cv2.resize(face_img, (64, 64)) if cv2 is not None else np.array(face_img)
            if len(resized.shape) == 3:
                gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY) if cv2 is not None else resized.mean(axis=2)
            else:
                gray = resized
            # 8x8 block means -> 64 values + 64 histogram bins = 128 values
            blocks = cv2.resize(gray, (8, 8)).flatten()
            hist, _ = np.histogram(gray, bins=64, range=(0, 256))
            feat = np.concatenate([blocks, hist]).astype(np.float32)
            norm = np.linalg.norm(feat)
            if norm > 0:
                feat = feat / norm
            return feat
        except Exception as e:
            logger.error("Feature extraction error: %s", e)
            return None

    def enroll(self, profile_name: str, features_list: list[np.ndarray]) -> bool:
        """Saves averaged vector embedding for a profile."""
        if not features_list:
            return False
        valid = [np.asarray(f).flatten() for f in features_list if f is not None]
        if not valid:
            return False
        avg_vec = np.mean(valid, axis=0)
        norm = np.linalg.norm(avg_vec)
        if norm > 0:
            avg_vec = avg_vec / norm

        self._profiles[profile_name] = {
            "name": profile_name,
            "samples": len(valid),
            "enrolled_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "vector": avg_vec.tolist(),
        }
        self.save()
        return True

    def match(self, candidate_feat: np.ndarray, profile_name: str = "master",
              threshold: float = 0.363) -> tuple[bool, float]:
        """Calculates cosine similarity with enrolled profile. Returns (is_match, similarity)."""
        if candidate_feat is None or profile_name not in self._profiles:
            return False, 0.0

        target_vec = np.array(self._profiles[profile_name]["vector"], dtype=np.float32)
        cand_vec = np.array(candidate_feat, dtype=np.float32).flatten()

        norm_t = np.linalg.norm(target_vec)
        norm_c = np.linalg.norm(cand_vec)
        if norm_t == 0 or norm_c == 0:
            return False, 0.0

        cosine_sim = float(np.dot(target_vec, cand_vec) / (norm_t * norm_c))
        is_match = cosine_sim >= threshold
        return is_match, round(cosine_sim, 4)

    def is_enrolled(self, profile_name: str = "master") -> bool:
        return profile_name in self._profiles

    def get_profiles(self) -> list[str]:
        return list(self._profiles.keys())

    def delete_profile(self, profile_name: str) -> bool:
        if profile_name in self._profiles:
            del self._profiles[profile_name]
            self.save()
            return True
        return False


class PrivacyShield:
    """Detects and minimizes sensitive windows when unauthorized or shoulder-surfing presence occurs."""

    def __init__(self, sensitive_keywords: list[str] | None = None) -> None:
        self.keywords = [k.lower() for k in (sensitive_keywords or DEFAULT_SHIELD_KEYWORDS)]
        self._minimized_hwnds: list[tuple[int, str]] = []
        self._lock = threading.Lock()
        self.is_shielded = False

    def activate(self, custom_keywords: list[str] | None = None) -> list[str]:
        """Minimizes visible windows matching sensitive keywords and records them for restoration."""
        with self._lock:
            active_keywords = [k.lower() for k in (custom_keywords or self.keywords)]
            minimized_titles: list[str] = []

            if win32gui is None or win32con is None:
                self.is_shielded = True
                return ["simulated_shield_active"]

            def enum_cb(hwnd: int, extra: Any) -> bool:
                if not win32gui.IsWindowVisible(hwnd):
                    return True
                title = win32gui.GetWindowText(hwnd).strip()
                if not title:
                    return True
                lower_title = title.lower()
                for kw in active_keywords:
                    if kw in lower_title:
                        try:
                            # Minimize matching window
                            win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
                            self._minimized_hwnds.append((hwnd, title))
                            minimized_titles.append(title)
                        except Exception as e:
                            logger.debug("Failed to minimize hwnd %s (%s): %s", hwnd, title, e)
                        break
                return True

            try:
                win32gui.EnumWindows(enum_cb, None)
            except Exception as e:
                logger.error("EnumWindows failed during shield activation: %s", e)

            self.is_shielded = True
            return minimized_titles

    def deactivate(self) -> int:
        """Restores previously minimized windows."""
        with self._lock:
            if not self._minimized_hwnds:
                self.is_shielded = False
                return 0

            restored_count = 0
            if win32gui is not None and win32con is not None:
                for hwnd, _ in self._minimized_hwnds:
                    try:
                        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                        restored_count += 1
                    except Exception as e:
                        logger.debug("Failed to restore hwnd %s: %s", hwnd, e)

            self._minimized_hwnds.clear()
            self.is_shielded = False
            return restored_count

    def status(self) -> dict:
        return {
            "is_shielded": self.is_shielded,
            "minimized_windows_count": len(self._minimized_hwnds),
            "keywords": self.keywords,
        }


class PresenceWatcher:
    """Autonomous physical presence sentry loop running at ~1 FPS."""

    def __init__(
        self,
        config: dict | None = None,
        profile_mgr: FaceProfileManager | None = None,
        shield: PrivacyShield | None = None,
        notifier: Any = None,
        detector_model_path: str | Path = "data/face_detection_yunet.onnx",
    ) -> None:
        self.config = (config or {}).get("biometrics") or {}
        self.profile_mgr = profile_mgr or FaceProfileManager()
        self.shield = shield or PrivacyShield()
        self.notifier = notifier
        self.detector_model_path = Path(detector_model_path)

        # Configurable parameters
        self.enabled = bool(self.config.get("enabled", True))
        self.auto_lock_enabled = bool(self.config.get("auto_lock", False))
        self.lock_timeout_sec = int(self.config.get("lock_timeout_sec", 60))
        self.shoulder_surf_shield = bool(self.config.get("shoulder_surf_shield", True))
        self.camera_index = int(self.config.get("camera_index", 0))
        self.interval_s = float(self.config.get("interval_s", 1.0))

        # Runtime state
        self.state = "INITIALIZING"  # PRESENT_MASTER, PRESENT_UNKNOWN, SHOULDER_SURF, AWAY, UNKNOWN
        self.active_faces = 0
        self.master_detected = False
        self.last_seen_master = time.time()
        self.away_start_time: float | None = None
        self.lock_triggered = False
        self.camera_available = False

        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._detector = None
        self._cap = None
        self._test_frame_override: tuple[int, bool] | None = None
        self.mock_lock_callback: Callable[[], None] | None = None

        self._init_detector()

    def _init_detector(self) -> None:
        if cv2 is not None and hasattr(cv2, "FaceDetectorYN") and self.detector_model_path.exists():
            try:
                # YuNet with input size 320x320
                self._detector = cv2.FaceDetectorYN.create(
                    str(self.detector_model_path), "", (320, 320),
                    score_threshold=0.6, nms_threshold=0.3, top_k=5000
                )
            except Exception as e:
                logger.warning("Could not initialize YuNet detector: %s", e)
                self._detector = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_loop, name="lumi-biometrics-sentry", daemon=True)
        self._thread.start()
        logger.info("Biometric PresenceWatcher sentry started (interval=%.1fs)", self.interval_s)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None
        logger.info("Biometric PresenceWatcher stopped.")

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def set_test_frame(self, num_faces: int, is_master: bool = True) -> None:
        """Sets a test override for face count and master match (used in headless/test environments)."""
        self._test_frame_override = (num_faces, is_master)

    def clear_test_frame(self) -> None:
        self._test_frame_override = None

    def _acquire_camera(self) -> bool:
        if cv2 is None:
            self.camera_available = False
            return False
        if self._cap is None:
            try:
                self._cap = cv2.VideoCapture(self.camera_index)
                if not self._cap.isOpened():
                    self.camera_available = False
                    return False
            except Exception as e:
                logger.debug("Camera open error: %s", e)
                self.camera_available = False
                return False
        self.camera_available = True
        return True

    def _detect_faces_frame(self, frame: np.ndarray) -> list[tuple[Any, np.ndarray]]:
        """Returns list of (landmarks/box, face_crop)."""
        if frame is None or self._detector is None:
            return []

        h, w = frame.shape[:2]
        self._detector.setInputSize((w, h))
        _, faces = self._detector.detect(frame)
        if faces is None:
            return []

        results = []
        for face in faces:
            box = face[0:4].astype(int)
            x, y, bw, bh = box
            x = max(0, x)
            y = max(0, y)
            crop = frame[y:y + bh, x:x + bw]
            results.append((face, crop))
        return results

    def _lock_workstation(self) -> None:
        """Executes workstation lock via user32.LockWorkStation."""
        logger.warning("LUMI Biometric Sentry: Auto-locking workstation due to prolonged absence.")
        if self.mock_lock_callback is not None:
            self.mock_lock_callback()
            return

        try:
            ctypes.windll.user32.LockWorkStation()
        except Exception as e:
            logger.error("Failed to lock workstation: %s", e)

    def _emit_alert(self, severity: str, rule: str, message: str) -> None:
        if self.notifier and hasattr(self.notifier, "emit"):
            try:
                self.notifier.emit(severity, rule, message, dedupe_key=f"biometrics:{rule}")
            except Exception as e:
                logger.debug("Notifier error: %s", e)

    def _run_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as e:
                logger.error("Error in presence watcher tick: %s", e)
            self._stop.wait(self.interval_s)

    def tick(self) -> None:
        """Single evaluation step of physical presence."""
        if not self.enabled:
            self.state = "DISABLED"
            return

        num_faces = 0
        master_matched = False

        if self._test_frame_override is not None:
            num_faces, master_matched = self._test_frame_override
        else:
            if not self._acquire_camera():
                self.state = "CAMERA_UNAVAILABLE"
                return

            ret, frame = self._cap.read()
            if not ret or frame is None:
                self.state = "CAMERA_NO_FRAME"
                return

            detected = self._detect_faces_frame(frame)
            num_faces = len(detected)

            if num_faces > 0:
                for face_data, crop in detected:
                    feat = self.profile_mgr.extract_features(frame, face_data)
                    is_match, _ = self.profile_mgr.match(feat, "master")
                    if is_match:
                        master_matched = True
                        break

        self.active_faces = num_faces
        self.master_detected = master_matched
        now = time.time()

        # State machine evaluation
        if num_faces == 0:
            if self.away_start_time is None:
                self.away_start_time = now
            away_dur = now - self.away_start_time
            self.state = "AWAY"

            if self.auto_lock_enabled and not self.lock_triggered and away_dur >= self.lock_timeout_sec:
                self.lock_triggered = True
                self._lock_workstation()
                self._emit_alert("WARN", "BIOMETRIC_AUTOLOCK",
                                 f"Workstation auto-locked: Master absent for {int(away_dur)}s.")

        elif num_faces >= 2:
            # SHOULDER-SURFING DETECTED!
            self.state = "SHOULDER_SURF"
            self.away_start_time = None
            self.lock_triggered = False

            if self.shoulder_surf_shield and not self.shield.is_shielded:
                shielded_wins = self.shield.activate()
                self._emit_alert("CRITICAL", "SHOULDER_SURFER_ALERT",
                                 f"Privacy Shield activated: {num_faces} faces detected in view ({len(shielded_wins)} windows minimized).")

        else:
            # Exactly 1 face
            self.away_start_time = None
            self.lock_triggered = False

            if master_matched:
                prev_state = self.state
                self.state = "PRESENT_MASTER"
                self.last_seen_master = now

                # If returning after being away or if shield was active
                if prev_state in ("AWAY", "SHOULDER_SURF") and self.shield.is_shielded:
                    restored = self.shield.deactivate()
                    logger.info("Restored %s windows upon master return.", restored)

                if prev_state == "AWAY":
                    self._emit_alert("INFO", "MASTER_WELCOME", "Welcome back, Boss! Biometric presence confirmed.")

            else:
                self.state = "PRESENT_UNKNOWN"
                self._emit_alert("WARN", "UNKNOWN_VIEWER", "Unenrolled face detected in front of terminal.")

    def get_telemetry(self) -> dict:
        """Returns current live presence and sentry state."""
        now = time.time()
        away_sec = round(now - self.away_start_time, 1) if self.away_start_time else 0.0
        return {
            "enabled": self.enabled,
            "state": self.state,
            "active_faces": self.active_faces,
            "master_detected": self.master_detected,
            "is_enrolled": self.profile_mgr.is_enrolled("master"),
            "is_shielded": self.shield.is_shielded,
            "minimized_windows_count": len(self.shield._minimized_hwnds),
            "away_duration_seconds": away_sec,
            "auto_lock_enabled": self.auto_lock_enabled,
            "lock_timeout_sec": self.lock_timeout_sec,
            "shoulder_surf_shield_enabled": self.shoulder_surf_shield,
            "camera_available": self.camera_available or (self._test_frame_override is not None),
        }

    def set_config(self, enabled: bool | None = None, auto_lock: bool | None = None,
                   lock_timeout_sec: int | None = None, shoulder_surf_shield: bool | None = None) -> dict:
        if enabled is not None:
            self.enabled = bool(enabled)
        if auto_lock is not None:
            self.auto_lock_enabled = bool(auto_lock)
        if lock_timeout_sec is not None:
            self.lock_timeout_sec = max(5, int(lock_timeout_sec))
        if shoulder_surf_shield is not None:
            self.shoulder_surf_shield = bool(shoulder_surf_shield)
        return self.get_telemetry()


_global_watcher: PresenceWatcher | None = None


def get_presence_watcher(config: dict | None = None, notifier: Any = None) -> PresenceWatcher:
    global _global_watcher
    if _global_watcher is None:
        _global_watcher = PresenceWatcher(config=config, notifier=notifier)
    return _global_watcher

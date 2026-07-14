"""Local speech-to-text for OPERATOR (push-to-talk voice input).

Transcription uses faster-whisper (CTranslate2 — no torch, runs on CPU) and
microphone capture uses sounddevice. Both are optional: if either package is
missing, or there is no input device, voice input disables itself cleanly and
the rest of OPERATOR keeps working.

Design notes:
- The Whisper model loads lazily on first use (``ensure_model``) so startup
  stays fast; ``prewarm`` can load it on a background thread if desired.
- ``record_until_silence`` auto-stops after a short trailing silence, so the
  user just speaks and pauses — no second keypress required. A ``stop`` flag
  lets a caller end recording early (e.g. pressing the hotkey again).
- Everything is defensive: any capture/transcription error returns "" or None
  rather than raising, so a flaky mic never crashes the overlay or REPL.
"""

import threading
from typing import Optional

from logger_config import op_logger

try:
    import numpy as np
    import sounddevice as sd
    _AUDIO_OK = True
except Exception:  # ImportError, or PortAudio failing to load
    np = None
    sd = None
    _AUDIO_OK = False

try:
    from faster_whisper import WhisperModel
    _WHISPER_OK = True
except Exception:
    WhisperModel = None
    _WHISPER_OK = False


SAMPLE_RATE = 16000       # Whisper expects 16 kHz mono
CHUNK_SECONDS = 0.1       # granularity of the record/silence loop


class VoiceInput:
    """Microphone → text via a locally-run Whisper model."""

    def __init__(self, model_size: str = "base"):
        self.model_size = model_size
        self._model = None
        self._model_lock = threading.Lock()
        self._stop_flag = threading.Event()

    # ==================== Availability ====================

    @staticmethod
    def dependencies_available() -> bool:
        """True if the Python packages needed for voice are importable."""
        return _AUDIO_OK and _WHISPER_OK

    @staticmethod
    def _has_input_device() -> bool:
        if not _AUDIO_OK:
            return False
        try:
            return any(d.get("max_input_channels", 0) > 0 for d in sd.query_devices())
        except Exception:
            return False

    def is_available(self) -> bool:
        """True only if voice can actually run right now (deps + a mic)."""
        return self.dependencies_available() and self._has_input_device()

    def unavailable_reason(self) -> str:
        """Human-readable explanation for why voice is off (or '' if it's on)."""
        if not _WHISPER_OK:
            return "faster-whisper not installed (pip install -r requirements-voice.txt)"
        if not _AUDIO_OK:
            return "sounddevice/numpy not installed (pip install -r requirements-voice.txt)"
        if not self._has_input_device():
            return "no microphone detected"
        return ""

    # ==================== Model loading ====================

    def model_ready(self) -> bool:
        return self._model is not None

    def ensure_model(self):
        """Load the Whisper model (blocking, idempotent). Returns the model."""
        if self._model is not None:
            return self._model
        with self._model_lock:
            if self._model is None:
                op_logger.logger.info(f"Loading Whisper model '{self.model_size}'...")
                self._model = WhisperModel(
                    self.model_size, device="cpu", compute_type="int8"
                )
                op_logger.logger.info("Whisper model ready")
        return self._model

    def prewarm(self):
        """Load the model on a background thread so first use is instant."""
        if not self.dependencies_available() or self._model is not None:
            return
        threading.Thread(target=self._safe_prewarm, daemon=True).start()

    def _safe_prewarm(self):
        try:
            self.ensure_model()
        except Exception:
            op_logger.logger.exception("Whisper prewarm failed")

    # ==================== Recording ====================

    def stop(self):
        """Signal an in-progress ``record_until_silence`` to finish now."""
        self._stop_flag.set()

    def record_until_silence(
        self,
        max_seconds: float = 15.0,
        silence_seconds: float = 1.2,
        start_timeout: float = 6.0,
        threshold: float = 0.015,
    ):
        """Capture mic audio until a trailing pause (or a hard cap).

        Returns a float32 numpy array of samples, or None if the user never
        started speaking / nothing was captured.
        """
        if not _AUDIO_OK:
            return None

        self._stop_flag.clear()
        chunk = int(CHUNK_SECONDS * SAMPLE_RATE)
        silence_needed = int(silence_seconds / CHUNK_SECONDS)
        max_chunks = int(max_seconds / CHUNK_SECONDS)
        start_chunks = int(start_timeout / CHUNK_SECONDS)

        frames = []
        silent = 0
        speaking = False
        try:
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32") as stream:
                for i in range(max_chunks):
                    if self._stop_flag.is_set():
                        break
                    data, _ = stream.read(chunk)
                    mono = data.reshape(-1)
                    frames.append(mono.copy())
                    rms = float(np.sqrt(np.mean(mono ** 2))) if mono.size else 0.0
                    if rms > threshold:
                        speaking = True
                        silent = 0
                    else:
                        silent += 1
                    # Stop once the user has spoken and then paused
                    if speaking and silent >= silence_needed:
                        break
                    # Give up if nobody speaks within the start window
                    if not speaking and i >= start_chunks:
                        break
        except Exception:
            op_logger.logger.exception("Microphone capture failed")
            return None

        if not speaking or not frames:
            return None
        return np.concatenate(frames)

    # ==================== Transcription ====================

    def transcribe(self, audio) -> str:
        """Transcribe a numpy audio buffer to text (returns '' on any failure)."""
        if audio is None or not _WHISPER_OK:
            return ""
        try:
            model = self.ensure_model()
            segments, _info = model.transcribe(
                audio, language="en", vad_filter=True, beam_size=1
            )
            return " ".join(seg.text.strip() for seg in segments).strip()
        except Exception:
            op_logger.logger.exception("Transcription failed")
            return ""

    def listen(self, **kwargs) -> str:
        """Record then transcribe in one call (blocking). Returns the text."""
        audio = self.record_until_silence(**kwargs)
        return self.transcribe(audio)

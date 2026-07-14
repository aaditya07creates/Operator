"""Voice input tests — cover availability logic and guards without touching
any real microphone, model download, or network."""

import numpy as np
import pytest

import voice_input
from voice_input import VoiceInput


def test_transcribe_none_returns_empty():
    assert VoiceInput().transcribe(None) == ""


def test_unavailable_reason_when_whisper_missing(monkeypatch):
    monkeypatch.setattr(voice_input, "_WHISPER_OK", False)
    v = VoiceInput()
    assert not v.dependencies_available()
    assert "faster-whisper" in v.unavailable_reason()


def test_unavailable_reason_when_audio_missing(monkeypatch):
    monkeypatch.setattr(voice_input, "_WHISPER_OK", True)
    monkeypatch.setattr(voice_input, "_AUDIO_OK", False)
    v = VoiceInput()
    assert not v.dependencies_available()
    assert "sounddevice" in v.unavailable_reason()


def test_unavailable_reason_when_no_microphone(monkeypatch):
    monkeypatch.setattr(voice_input, "_WHISPER_OK", True)
    monkeypatch.setattr(voice_input, "_AUDIO_OK", True)
    monkeypatch.setattr(VoiceInput, "_has_input_device", staticmethod(lambda: False))
    v = VoiceInput()
    assert v.dependencies_available()
    assert not v.is_available()
    assert v.unavailable_reason() == "no microphone detected"


def test_available_when_everything_present(monkeypatch):
    monkeypatch.setattr(voice_input, "_WHISPER_OK", True)
    monkeypatch.setattr(voice_input, "_AUDIO_OK", True)
    monkeypatch.setattr(VoiceInput, "_has_input_device", staticmethod(lambda: True))
    v = VoiceInput()
    assert v.is_available()
    assert v.unavailable_reason() == ""


def test_record_returns_none_without_audio_backend(monkeypatch):
    # With no audio backend, recording must degrade to None, never raise.
    monkeypatch.setattr(voice_input, "_AUDIO_OK", False)
    assert VoiceInput().record_until_silence() is None


def test_stop_flag_roundtrips():
    v = VoiceInput()
    assert not v._stop_flag.is_set()
    v.stop()
    assert v._stop_flag.is_set()


def test_transcribe_on_silence_buffer_is_safe(monkeypatch):
    # If whisper isn't importable in the test env, transcribe still must not raise.
    monkeypatch.setattr(voice_input, "_WHISPER_OK", False)
    out = VoiceInput().transcribe(np.zeros(1600, dtype="float32"))
    assert out == ""

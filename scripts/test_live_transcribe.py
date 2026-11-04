"""Test live /api/transcribe HTTP endpoint with wave audio data."""

import math
import struct
import tempfile
import os
import requests

def main():
    tf = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    tf.close()

    import wave
    w = wave.open(tf.name, "wb")
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(16000)
    for i in range(16000):
        val = int(10000 * math.sin(2 * math.pi * 440 * i / 16000))
        w.writeframes(struct.pack("<h", val))
    w.close()

    try:
        with open(tf.name, "rb") as f:
            resp = requests.post("http://127.0.0.1:8765/api/transcribe", files={"file": ("test.wav", f, "audio/wav")})
        print("STATUS:", resp.status_code)
        print("JSON:", resp.json())
    finally:
        try:
            os.unlink(tf.name)
        except Exception:
            pass

if __name__ == "__main__":
    main()

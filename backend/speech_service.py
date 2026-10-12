"""
Speech-to-Text Service.
Provides a unified provider abstraction (Groq Whisper, OpenAI Whisper, Mock).
Validates audio size, format, performs atomic temporary file cleanup, and handles language hints.
Never leaks provider credentials to clients.
"""
import os
import tempfile
import urllib.request
import urllib.error
import mimetypes
import json
from typing import Dict, Any, Optional
from dotenv import load_dotenv
load_dotenv()

ALLOWED_CONTENT_TYPES = {
    "audio/webm",
    "audio/wav",
    "audio/wave",
    "audio/x-wav",
    "audio/mp3",
    "audio/mpeg",
    "audio/mp4",
    "audio/m4a",
    "audio/x-m4a",
    "audio/ogg",
    "audio/aac",
    "application/octet-stream"  # Mobile browser edge cases
}

MAX_AUDIO_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB limit (plenty for short 10-15s transaction clips)

class SpeechServiceError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code

def transcribe_audio(
    audio_bytes: bytes,
    content_type: str,
    language_hint: str = "te",
    mock_transcript: Optional[str] = None
) -> Dict[str, Any]:
    """
    Transcribes audio bytes to text using configured provider.
    Returns:
    {
        "transcript": str,
        "language": str,
        "provider": str
    }
    """
    # 1. Mock transcript override (for tests or development)
    if mock_transcript:
        return {
            "transcript": mock_transcript.strip(),
            "language": language_hint,
            "provider": "mock"
        }

    # 2. Validation
    if not audio_bytes:
        raise SpeechServiceError("Empty audio payload received.", status_code=400)

    if len(audio_bytes) > MAX_AUDIO_SIZE_BYTES:
        raise SpeechServiceError("Audio recording exceeds the 10 MB limit.", status_code=413)

    if content_type and content_type.lower() not in ALLOWED_CONTENT_TYPES:
        raise SpeechServiceError(f"Unsupported audio format: {content_type}.", status_code=415)

    provider = os.getenv("SPEECH_PROVIDER", "").lower()
    api_key = os.getenv("SPEECH_API_KEY") or os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY")

    # If no provider or API key is set, fail with clear actionable error
    if not api_key:
        raise SpeechServiceError(
            "Speech provider API key is not configured on the server. Please add GROQ_API_KEY to your environment variables.",
            status_code=500
        )

    # Determine file extension for temporary file
    ext = ".webm"
    if "wav" in content_type:
        ext = ".wav"
    elif "mp4" in content_type or "m4a" in content_type:
        ext = ".m4a"
    elif "ogg" in content_type:
        ext = ".ogg"
    elif "mp3" in content_type or "mpeg" in content_type:
        ext = ".mp3"

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp_file:
            tmp_file.write(audio_bytes)
            tmp_path = tmp_file.name

        # Call Whisper endpoint (Groq or OpenAI)
        if provider == "groq" or (not provider and os.getenv("GROQ_API_KEY")):
            return _transcribe_groq(tmp_path, api_key, language_hint)
        else:
            return _transcribe_openai(tmp_path, api_key, language_hint)

    except SpeechServiceError:
        raise
    except Exception as e:
        # Avoid leaking internal secrets in logs or responses
        raise SpeechServiceError("Speech transcription failed. Please try again or use manual entry.", status_code=502)
    finally:
        # Safe cleanup of temporary audio file
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass

def _transcribe_groq(file_path: str, api_key: str, language_hint: str) -> Dict[str, Any]:
    """Transcribe using Groq Whisper (ultra low latency, high accuracy on Indic code-switching)."""
    import urllib.request
    import mimetypes
    import json

    boundary = "----WebKitFormBoundaryVoiceKhata7MA4YWxkTrZu0gW"
    data = []

    # model field
    data.append(f"--{boundary}".encode())
    data.append(b'Content-Disposition: form-data; name="model"')
    data.append(b'')
    data.append(b'whisper-large-v3')

    # language field (optional hint)
    if language_hint in ["te", "hi", "en"]:
        data.append(f"--{boundary}".encode())
        data.append(b'Content-Disposition: form-data; name="language"')
        data.append(b'')
        data.append(language_hint.encode())

    # prompt hint for kirana domain
    data.append(f"--{boundary}".encode())
    data.append(b'Content-Disposition: form-data; name="prompt"')
    data.append(b'')
    data.append(b'Kirana shop credit/udhara transaction. Names: Ramesh, Suresh, Anitha, Ravi, Mahesh. Phrases: udhar, credit, payment, jama, appu, chellimpu, rupees, rupayalu, 100, 200, 500.')

    # file field
    with open(file_path, "rb") as f:
        file_bytes = f.read()

    data.append(f"--{boundary}".encode())
    data.append(b'Content-Disposition: form-data; name="file"; filename="audio.webm"')
    data.append(b'Content-Type: audio/webm')
    data.append(b'')
    data.append(file_bytes)
    data.append(f"--{boundary}--".encode())
    data.append(b'')

    body = b"\r\n".join(data)

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/audio/transcriptions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "KiranaKhataApp/1.0"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
            return {
                "transcript": result.get("text", "").strip(),
                "language": language_hint,
                "provider": "groq"
            }
    except urllib.error.HTTPError as he:
        err_body = he.read().decode("utf-8", errors="ignore")
        print(f"[Groq Whisper API HTTPError {he.code}]: {err_body}")
        raise SpeechServiceError(f"Groq transcription error ({he.code}): {err_body}", status_code=502)

def _transcribe_openai(file_path: str, api_key: str, language_hint: str) -> Dict[str, Any]:
    """Transcribe using OpenAI Whisper."""
    import urllib.request
    import json

    boundary = "----WebKitFormBoundaryVoiceKhataOpenAI"
    data = []

    # model field
    data.append(f"--{boundary}".encode())
    data.append(b'Content-Disposition: form-data; name="model"')
    data.append(b'')
    data.append(b'whisper-1')

    if language_hint in ["te", "hi", "en"]:
        data.append(f"--{boundary}".encode())
        data.append(b'Content-Disposition: form-data; name="language"')
        data.append(b'')
        data.append(language_hint.encode())

    # file field
    with open(file_path, "rb") as f:
        file_bytes = f.read()

    data.append(f"--{boundary}".encode())
    data.append(b'Content-Disposition: form-data; name="file"; filename="audio.webm"')
    data.append(b'Content-Type: audio/webm')
    data.append(b'')
    data.append(file_bytes)
    data.append(f"--{boundary}--".encode())
    data.append(b'')

    body = b"\r\n".join(data)

    req = urllib.request.Request(
        "https://api.openai.com/v1/audio/transcriptions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "KiranaKhataApp/1.0"
        }
    )

    with urllib.request.urlopen(req, timeout=15) as response:
        result = json.loads(response.read().decode("utf-8"))
        return {
            "transcript": result.get("text", "").strip(),
            "language": language_hint,
            "provider": "openai"
        }

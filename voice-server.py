"""
Combined STT + TTS Voice Server
- STT: Faster-Whisper with Arabic-English code-switching model (CUDA)
- TTS: Supertonic 3 via Python SDK (direct, no separate server)

Usage:
    stt-env\Scripts\python.exe voice-server.py

Configuration (environment variables):
    VOICE_PORT       - Server port (default: 7790)
    VOICE_HOST       - Bind address (default: 127.0.0.1)
    CUDA_DEVICE      - GPU index for STT model (default: auto-detect)

Open http://127.0.0.1:7790/ for the web UI.
"""

import os
import sys
import time
import io
import asyncio
import tempfile
import traceback
import numpy as np
import soundfile as sf
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# ═══════════════════════════════════════════════════════════════════
#  Configuration
# ═══════════════════════════════════════════════════════════════════
SERVER_PORT = int(os.environ.get("VOICE_PORT", 7790))
SERVER_HOST = os.environ.get("VOICE_HOST", "127.0.0.1")
CUDA_DEVICE = os.environ.get("CUDA_DEVICE", None)  # None = auto-detect

# ═══════════════════════════════════════════════════════════════════
#  Load TTS Model (Supertonic)
# ═══════════════════════════════════════════════════════════════════
print("=" * 60)
print("  Loading TTS model (Supertonic 3)...")
print("=" * 60)
from supertonic import TTS

tts_engine = TTS(auto_download=True)
TTS_SAMPLE_RATE = getattr(tts_engine, "sample_rate", 44100)
TTS_VOICES = ["M1", "M2", "M3", "M4", "M5", "F1", "F2", "F3", "F4", "F5"]

# Pre-load default voice style
default_style = tts_engine.get_voice_style(voice_name="M1")
print(f"[TTS] Supertonic loaded! Sample rate: {TTS_SAMPLE_RATE}, Voices: {TTS_VOICES}")
sys.stdout.flush()

# ═══════════════════════════════════════════════════════════════════
#  Load STT Model (Faster-Whisper)
# ═══════════════════════════════════════════════════════════════════
print("=" * 60)
print("  Loading STT model (Arabic-English code-switching)...")
print("=" * 60)
from faster_whisper import WhisperModel

stt_model = None
stt_device = "unknown"

# Try CUDA with configured or auto-detected device index
cuda_indices = [int(CUDA_DEVICE)] if CUDA_DEVICE is not None else [0, 1, 2]
for idx in cuda_indices:
    try:
        stt_model = WhisperModel("whisper-ar-en", device="cuda", device_index=idx, compute_type="int8")
        stt_device = f"cuda (GPU {idx})"
        print(f"[STT] Model loaded on {stt_device}!")
        break
    except Exception as e:
        print(f"[STT] CUDA GPU {idx} failed: {e}")

if stt_model is None:
    print("[STT] All CUDA attempts failed, falling back to CPU...")
    stt_model = WhisperModel("whisper-ar-en", device="cpu", compute_type="int8")
    stt_device = "cpu"
    print("[STT] Model loaded on CPU.")

sys.stdout.flush()

# Thread pool for blocking model calls (STT/TTS inference)
from concurrent.futures import ThreadPoolExecutor
thread_pool = ThreadPoolExecutor(max_workers=2)

# ═══════════════════════════════════════════════════════════════════
#  FastAPI App
# ═══════════════════════════════════════════════════════════════════
app = FastAPI(title="VoxBridge — STT + TTS")

# Restrict CORS origins in production; allow all only for local dev
allowed_origins = ["*"] if SERVER_HOST in ("127.0.0.1", "localhost") else ["http://127.0.0.1", "http://localhost"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")


# ── Web UI ─────────────────────────────────────────────────────
@app.get("/")
async def root():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path, media_type="text/html")
    return {"error": "static/index.html not found"}


# Mount static directory for CSS/JS/images (but NOT the project root)
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/api/info")
async def info():
    return {
        "server": {
            "host": SERVER_HOST,
            "port": SERVER_PORT,
        },
        "stt": {
            "status": "ok",
            "model": "faster-whisper-large-v2-ar-codeswitching",
            "device": stt_device,
        },
        "tts": {
            "status": "ok",
            "model": "supertonic-3",
            "sample_rate": TTS_SAMPLE_RATE,
            "voices": TTS_VOICES,
        },
    }


# ═══════════════════════════════════════════════════════════════════
#  STT Endpoints
# ═══════════════════════════════════════════════════════════════════

@app.post("/v1/audio/transcriptions")
async def stt_openai(
    file: UploadFile = File(...),
    language: str = Form(default=None),
    response_format: str = Form(default="json"),
):
    """OpenAI-compatible STT endpoint."""
    return await _transcribe(file, language=language, response_format=response_format)


@app.post("/api/stt")
async def stt_simple(file: UploadFile = File(...)):
    """Simple STT endpoint."""
    return await _transcribe(file)


async def _transcribe(file: UploadFile, language: str = None, response_format: str = "json"):
    start_time = time.time()
    print(f"\n[STT] Received: {file.filename} ({file.content_type})")
    sys.stdout.flush()

    try:
        audio_bytes = await file.read()
        print(f"[STT] Audio: {len(audio_bytes)} bytes")
        sys.stdout.flush()

        suffix = ".webm"
        if file.content_type:
            ct = file.content_type.lower()
            if "wav" in ct:
                suffix = ".wav"
            elif "ogg" in ct:
                suffix = ".ogg"
            elif "mp3" in ct or "mpeg" in ct:
                suffix = ".mp3"
            elif "webm" in ct:
                suffix = ".webm"
            elif "mp4" in ct or "m4a" in ct:
                suffix = ".mp4"

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            # Build transcription kwargs
            transcribe_kwargs = {
                "beam_size": 5,
                "vad_filter": True,
                "initial_prompt": "بسم الله الرحمن الرحيم، السلام عليكم ورحمة الله وبركاته",
                "condition_on_previous_text": False,
            }
            # Apply language hint if provided (e.g., "ar", "en")
            if language and language.strip():
                lang = language.strip().lower()[:2]
                transcribe_kwargs["language"] = lang
                print(f"[STT] Language hint: {lang}")

            # Run blocking transcription in thread pool
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                thread_pool,
                lambda: _run_transcribe(tmp_path, transcribe_kwargs),
            )

            segments_list, info, full_text = result
            elapsed = round(time.time() - start_time, 2)
            print(f"[STT] Done in {elapsed}s | {info.language} ({round(info.language_probability*100,1)}%) | {full_text.strip()[:80]}")
            sys.stdout.flush()

            response_data = {
                "text": full_text.strip(),
                "language": info.language,
                "language_probability": round(info.language_probability, 4),
                "duration": round(info.duration, 2),
                "segments": segments_list,
                "processing_time": elapsed,
            }

            # Support verbose_json format for OpenAI compatibility
            if response_format == "verbose_json":
                response_data["task"] = "transcribe"
                response_data["words"] = []  # word-level timestamps not available

            return JSONResponse(content=response_data)
        finally:
            os.unlink(tmp_path)

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


def _run_transcribe(tmp_path: str, kwargs: dict):
    """Synchronous transcription — runs in thread pool."""
    segments, info = stt_model.transcribe(tmp_path, **kwargs)
    segment_list = []
    full_text = ""
    for seg in segments:
        segment_list.append({
            "start": round(seg.start, 2),
            "end": round(seg.end, 2),
            "text": seg.text.strip(),
        })
        full_text += seg.text + " "
    return segment_list, info, full_text


# ═══════════════════════════════════════════════════════════════════
#  TTS Endpoints (Direct via Supertonic SDK)
# ═══════════════════════════════════════════════════════════════════

@app.get("/v1/voices")
async def tts_voices():
    """List available TTS voices."""
    return JSONResponse(content={"voices": TTS_VOICES})


@app.get("/v1/styles")
async def tts_styles():
    """List TTS styles."""
    styles = [{"name": v, "kind": "builtin"} for v in TTS_VOICES]
    return JSONResponse(content={"styles": styles})


@app.post("/v1/audio/speech")
async def tts_speech(request_body: dict):
    """
    OpenAI-compatible TTS endpoint.
    Uses Supertonic SDK directly — no external server needed.
    """
    start_time = time.time()

    # Fix response_format
    fmt = request_body.get("response_format", "wav")
    if fmt not in {"wav", "flac", "ogg"}:
        print(f"\n[TTS] Converting response_format from '{fmt}' to 'wav'")
        fmt = "wav"

    text = request_body.get("input", request_body.get("text", ""))
    voice = request_body.get("voice", "M1")
    speed = float(request_body.get("speed", 1.0))
    if speed <= 0:
        speed = 1.0

    if not text:
        raise HTTPException(status_code=400, detail="No text provided")

    if voice not in TTS_VOICES:
        print(f"[TTS] Unknown voice '{voice}', using M1")
        voice = "M1"

    print(f"\n[TTS] Synthesizing: voice={voice}, speed={speed}, format={fmt}, text={text[:80]}...")
    sys.stdout.flush()

    try:
        # Get voice style
        try:
            voice_style = tts_engine.get_voice_style(voice_name=voice)
        except Exception:
            voice_style = default_style

        # Run blocking TTS in thread pool
        loop = asyncio.get_running_loop()
        wav_data, duration = await loop.run_in_executor(
            thread_pool,
            lambda: tts_engine.synthesize(text, voice_style=voice_style, lang="na"),
        )

        # Convert to numpy
        if hasattr(wav_data, 'cpu'):
            audio_np = wav_data.cpu().numpy()
        elif hasattr(wav_data, 'numpy'):
            audio_np = wav_data.numpy()
        else:
            audio_np = np.asarray(wav_data)

        audio_np = audio_np.squeeze().astype(np.float32)

        # Normalize
        max_val = np.max(np.abs(audio_np))
        if max_val > 1.0:
            audio_np = audio_np / max_val

        # Apply speed adjustment via resampling (changes tempo + pitch)
        if speed != 1.0 and speed > 0:
            new_length = int(len(audio_np) / speed)
            if new_length > 0:
                indices = np.linspace(0, len(audio_np) - 1, new_length)
                audio_np = np.interp(indices, np.arange(len(audio_np)), audio_np)
                # Recalculate duration for speed-adjusted audio
                duration = len(audio_np) / TTS_SAMPLE_RATE
                print(f"[TTS] Speed adjusted: {speed}x -> {round(duration, 2)}s audio")

        # Convert to int16
        audio_int16 = (audio_np * 32767).astype(np.int16)

        # Write to buffer
        buf = io.BytesIO()
        sf.write(buf, audio_int16, TTS_SAMPLE_RATE, format=fmt.upper())
        audio_bytes = buf.getvalue()

        content_type_map = {"wav": "audio/wav", "flac": "audio/flac", "ogg": "audio/ogg"}
        content_type = content_type_map.get(fmt, "audio/wav")

        elapsed = round(time.time() - start_time, 2)
        duration_val = float(np.asarray(duration).item())
        print(f"[TTS] Done in {elapsed}s | {len(audio_bytes)} bytes | {round(duration_val, 2)}s audio")
        sys.stdout.flush()

        return Response(
            content=audio_bytes,
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename=speech.{fmt}',
                "X-Audio-Duration": str(round(duration_val, 2)),
                "X-Processing-Time": str(elapsed),
                "X-Sample-Rate": str(TTS_SAMPLE_RATE),
            },
        )

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print()
    print("=" * 60)
    print(f"  ✅ Voice Server ready!")
    print(f"  🌐 Web UI:  http://{SERVER_HOST}:{SERVER_PORT}/")
    print(f"  📖 API docs: http://{SERVER_HOST}:{SERVER_PORT}/docs")
    print(f"  🎤 STT: POST /v1/audio/transcriptions")
    print(f"  🔊 TTS: POST /v1/audio/speech")
    print(f"  📡 Voices:  {', '.join(TTS_VOICES)}")
    print(f"  ⚡ STT device: {stt_device}")
    print("=" * 60)
    sys.stdout.flush()
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT)
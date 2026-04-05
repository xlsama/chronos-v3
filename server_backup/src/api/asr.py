from fastapi import APIRouter, HTTPException, UploadFile

from src.lib.logger import get_logger
from src.services.asr_service import transcribe_audio

log = get_logger()

router = APIRouter(prefix="/api/asr", tags=["asr"])


@router.post("/transcribe")
async def transcribe(file: UploadFile):
    audio_data = await file.read()
    if not audio_data:
        raise HTTPException(status_code=400, detail="空的音频文件")

    try:
        text = await transcribe_audio(audio_data, file.filename or "audio.webm")
    except Exception as e:
        log.error("ASR transcription failed", error=str(e))
        raise HTTPException(status_code=502, detail="语音识别失败") from e

    return {"text": text}

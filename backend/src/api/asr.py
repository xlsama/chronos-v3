import asyncio

import orjson
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.config import get_settings
from src.lib.logger import logger
from src.services.asr_service import ASRProxySession

router = APIRouter(prefix="/api/asr", tags=["asr"])


@router.websocket("/stream")
async def asr_stream(ws: WebSocket):
    await ws.accept()

    settings = get_settings()
    session = ASRProxySession(settings)

    try:
        await asyncio.wait_for(session.connect(), timeout=10)
    except Exception as e:
        logger.error(f"ASR: failed to connect upstream: {e}")
        await ws.send_json({"type": "error", "message": "ASR 服务连接失败"})
        await ws.close()
        return

    async def forward_audio():
        """Receive audio from client and forward to DashScope."""
        try:
            while True:
                data = await ws.receive()
                if data.get("type") == "websocket.disconnect":
                    break
                if "bytes" in data and data["bytes"]:
                    await session.send_audio(data["bytes"])
                elif "text" in data and data["text"]:
                    msg = orjson.loads(data["text"])
                    if msg.get("action") == "stop":
                        await session.finish_session()
                        break
        except WebSocketDisconnect:
            await session.finish_session()

    async def forward_results():
        """Receive results from DashScope and forward to client."""
        try:
            async for result in session.receive_results():
                await ws.send_json(result)
        except Exception as e:
            logger.error(f"ASR: upstream receive error: {e}")
            try:
                await ws.send_json({"type": "error", "message": str(e)})
            except Exception:
                pass

    audio_task = asyncio.create_task(forward_audio())
    results_task = asyncio.create_task(forward_results())

    try:
        done, pending = await asyncio.wait(
            [audio_task, results_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            # Give remaining task a few seconds to finish gracefully
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=5)
            except (asyncio.TimeoutError, Exception):
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
    except Exception as e:
        logger.error(f"ASR: session error: {e}")
        audio_task.cancel()
        results_task.cancel()
    finally:
        await session.close()
        try:
            await ws.close()
        except Exception:
            pass

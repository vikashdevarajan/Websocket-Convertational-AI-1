import uvicorn
import numpy as np
import torch
import os
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool
from datetime import datetime
from typing import Dict

from .services import llm_service, tts_service
from .services.stt_service import EnhancedVADAudioProcessor  # ✅ Fixed import
from .services.llm_service import Agent

# ADD THIS SECTION - FastAPI App Instance and Configuration
CONFIG = {
    "SAMPLE_RATE": 16000,
    "WHISPER_MODEL_NAME": "tiny.en",
    "SILENCE_THRESHOLD_RMS": 0.01,
    "VAD_PADDING_MS": 700,
    "MIN_SPEECH_DURATION_MS": 300,
    "OUTPUT_DIR": "realtime_audio_output",
    "LLM_MODEL": "gemini/gemini-2.0-flash"
}

# CREATE THE FASTAPI APP INSTANCE
app = FastAPI()

# ADD CORS MIDDLEWARE
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True, 
    allow_methods=["*"], 
    allow_headers=["*"]
)

# ADD STARTUP EVENT
@app.on_event("startup")
def load_models():
    """Load Whisper model and initialize LLM agent at startup."""
    import whisper
    print("Loading models...")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    app.state.whisper_model = whisper.load_model(CONFIG["WHISPER_MODEL_NAME"], device=device)
    
    app.state.llm_agent = Agent(
        name="Chat Assistant",
        model=CONFIG["LLM_MODEL"],
        tools=[],
        system_prompt="""You are a helpful assistant. Keep responses very concise and friendly. 
    IMPORTANT: Use only plain text without any formatting like asterisks, bullets, or special characters. 
    Avoid markdown formatting. Speak naturally as if in conversation. Keep responses under 50 words.""",
    to_break=None,
       
    )
    llm_service.set_global_agent(app.state.llm_agent)
    
    os.makedirs(CONFIG["OUTPUT_DIR"], exist_ok=True)
    print("✅ Server ready")

# Track active clients
clients: Dict[WebSocket, EnhancedVADAudioProcessor] = {}

# ADD YOUR WEBSOCKET ENDPOINT
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Handle WebSocket connections for real-time audio chat."""
    await websocket.accept()
    
    session_id = f"session-{len(clients)}"
    
    # Initialize VAD processor
    processor = EnhancedVADAudioProcessor(
        config=CONFIG, 
        whisper_model=app.state.whisper_model,
        websocket=websocket,
        session_id=session_id
    )
    
    clients[websocket] = processor
    print(f"Client {session_id} connected ({len(clients)} total)")
    
    # Send connection confirmation
    await websocket.send_text(json.dumps({
        "type": "connection",
        "status": "connected",
        "session_id": session_id,
        "message": "Ready"
    }))

    try:
        while True:
            pcm_bytes = await websocket.receive_bytes()
            audio_np = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            
            # Process audio chunk
            await processor.process_audio_chunk_async(audio_np)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"Error {session_id}: {str(e)[:50]}...")
        await websocket.send_text(json.dumps({
            "type": "error",
            "message": "Processing error"
        }))
    finally:
        if websocket in clients:
            del clients[websocket]
            print(f"Client {session_id} disconnected")

# ADD ROOT ENDPOINT (OPTIONAL)
@app.get("/")
def read_root():
    return {"status": "ok", "message": "Real-time Audio Chat API"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
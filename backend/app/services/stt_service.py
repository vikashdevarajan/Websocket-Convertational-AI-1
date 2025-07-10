import numpy as np
import collections
import whisper
import torch
import os
import json
from datetime import datetime
from scipy.io.wavfile import write as write_wav
from typing import Tuple, Optional
from fastapi.concurrency import run_in_threadpool

class EnhancedVADAudioProcessor:
    def __init__(self, config: dict, whisper_model, websocket, session_id: str):
        self.config = config
        self.whisper_model = whisper_model
        self.websocket = websocket
        self.session_id = session_id
        self.audio_buffer = collections.deque()
        self.is_speaking = False
        self.silence_counter = 0
        self.chunk_counter = 0
        self.speech_chunks = 0

    def is_speech_chunk(self, frame_data: np.ndarray) -> tuple[bool, float]:
        """Determine if audio chunk contains speech."""
        rms = np.sqrt(np.mean(frame_data**2))
        is_speech = rms > self.config["SILENCE_THRESHOLD_RMS"]
        return is_speech, rms

    async def send_status(self, status_type: str, data: dict):
        """Send status updates to frontend via WebSocket."""
        message = {
            "type": status_type,
            "session_id": self.session_id,
            **data
        }
        try:
            await self.websocket.send_text(json.dumps(message))
        except:
            pass  # Silent fail

    async def process_audio_chunk_async(self, audio_chunk: np.ndarray):
        """Process audio chunk asynchronously with minimal logging."""
        self.chunk_counter += 1
        
        is_speech, rms = self.is_speech_chunk(audio_chunk)
        
        if is_speech:
            if not self.is_speaking:
                self.is_speaking = True
                self.speech_chunks = 0
                # Only log when speech STARTS
                print(f"🎤 Speech started [{self.session_id}]")
                
                await self.send_status("speech_start", {
                    "rms": float(rms),
                    "threshold": self.config["SILENCE_THRESHOLD_RMS"]
                })
            
            self.audio_buffer.append(audio_chunk)
            self.speech_chunks += 1
            self.silence_counter = 0
            
        elif self.is_speaking:
            self.audio_buffer.append(audio_chunk)
            self.silence_counter += 1
            
            chunks_per_second = int(self.config["SAMPLE_RATE"] / len(audio_chunk)) if len(audio_chunk) > 0 else 10
            padding_chunks_needed = int((self.config["VAD_PADDING_MS"] / 1000) * chunks_per_second)
            
            if self.silence_counter >= padding_chunks_needed:
                # Only log when speech ENDS
                print(f"🛑 Speech ended [{self.session_id}]")
                self.is_speaking = False
                
                await self.send_status("speech_end", {
                    "speech_chunks": self.speech_chunks,
                    "silence_chunks": self.silence_counter
                })
                
                await self._process_complete_utterance()

    async def _process_complete_utterance(self):
        """Process complete utterance with minimal logging."""
        if not self.audio_buffer:
            return

        full_audio_np = np.concatenate(list(self.audio_buffer))
        self.audio_buffer.clear()

        min_samples = int((self.config["MIN_SPEECH_DURATION_MS"] / 1000.0) * self.config["SAMPLE_RATE"])
        if len(full_audio_np) < min_samples:
            await self.send_status("notification", {"message": "Audio too short"})
            return

        # Only log major processing steps
        print(f"📝 Processing [{self.session_id}]")
        
        try:
            # Save audio
            timestamp = datetime.now().strftime("%H%M%S")
            filename = f"utterance_{self.session_id}_{timestamp}.wav"
            file_path = os.path.join(self.config["OUTPUT_DIR"], filename)
            
            wav_data = (full_audio_np * 32767).astype(np.int16)
            write_wav(file_path, self.config["SAMPLE_RATE"], wav_data)

            # Transcribe
            def transcribe_audio():
                return self.whisper_model.transcribe(
                    full_audio_np.astype(np.float32), 
                    fp16=torch.cuda.is_available()
                )
            
            result = await run_in_threadpool(transcribe_audio)
            transcribed_text = result.get("text", "").strip()
            
            if not transcribed_text:
                await self.send_status("notification", {"message": "No speech detected"})
                return

            # Process with LLM
            def process_llm():
                from .llm_service import get_global_agent, process_llm
                agent = get_global_agent()
                return process_llm(agent, transcribed_text)
            
            llm_response = await run_in_threadpool(process_llm)

            # Generate TTS
            def generate_tts():
                from .tts_service import process_chatterbox
                return process_chatterbox(llm_response)
            
            tts_audio = await run_in_threadpool(generate_tts)

            # Send response
            await self.send_status("response", {
                "stt": transcribed_text,
                "llm": llm_response,
                "tts": tts_audio,
                "audio_file": filename
            })
            
            # Only log successful completion
            print(f"✅ Response sent [{self.session_id}]")

        except Exception as e:
            print(f"❌ Error [{self.session_id}]: {str(e)[:30]}...")
            await self.send_status("error", {"message": "Processing error"})
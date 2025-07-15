import numpy as np
import collections
import whisper
import torch
import re
import os
import json
from datetime import datetime
from scipy.io.wavfile import write as write_wav
from typing import Tuple, Optional
from fastapi.concurrency import run_in_threadpool
from .api_tts_service import process_api_tts


def clean_text_for_tts(text):
    # Remove all non-ASCII characters (keeps only plain English)
    return re.sub(r'[^\x00-\x7F]+', '', text)

class EnhancedVADAudioProcessor:
    """
    Handles Voice Activity Detection (VAD), buffering, transcription, LLM, and TTS for a single session.
    """

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
        """
        Determine if audio chunk contains speech using RMS threshold.
        Returns (is_speech, rms_value).
        """
        rms = np.sqrt(np.mean(frame_data**2))
        is_speech = rms > self.config["SILENCE_THRESHOLD_RMS"]
        return is_speech, rms

    async def send_status(self, status_type: str, data: dict):
        """
        Send status updates to frontend via WebSocket.
        """
        message = {
            "type": status_type,
            "session_id": self.session_id,
            **data
        }
        try:
            await self.websocket.send_text(json.dumps(message))
        except Exception:
            pass  # Silent fail

    async def process_audio_chunk_async(self, audio_chunk: np.ndarray):
        """
        Process audio chunk asynchronously, handle VAD and buffering.
        """
        self.chunk_counter += 1
        is_speech, rms = self.is_speech_chunk(audio_chunk)

        if is_speech:
            if not self.is_speaking:
                self.is_speaking = True
                self.speech_chunks = 0
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
                print(f"🛑 Speech ended [{self.session_id}]")
                self.is_speaking = False
                await self.send_status("speech_end", {
                    "speech_chunks": self.speech_chunks,
                    "silence_chunks": self.silence_counter
                })
                await self._process_complete_utterance()

    async def _process_complete_utterance(self):
        """
        Processes a complete utterance:
        - Saves the audio to disk
        - Transcribes with Whisper
        - Sends a response to the frontend (always, even if no speech detected)
        - If valid speech: gets LLM response, generates TTS, sends final response
        """
        if not self.audio_buffer:
            return

        # Concatenate all buffered audio chunks into a single numpy array
        full_audio_np = np.concatenate(list(self.audio_buffer))
        self.audio_buffer.clear()

        # Check if utterance is long enough to process
        min_samples = int((self.config["MIN_SPEECH_DURATION_MS"] / 1000.0) * self.config["SAMPLE_RATE"])
        if len(full_audio_np) < min_samples:
            await self.send_status("notification", {"message": "Audio too short"})
            return

        print(f"📝 Processing [{self.session_id}]")
        try:
            # 1. Save audio to disk
            timestamp = datetime.now().strftime("%H%M%S")
            filename = f"utterance_{self.session_id}_{timestamp}.wav"
            file_path = os.path.join(self.config["OUTPUT_DIR"], filename)
            wav_data = (full_audio_np * 32767).astype(np.int16)
            write_wav(file_path, self.config["SAMPLE_RATE"], wav_data)

            # 2. Transcribe with Whisper (runs in threadpool for async compatibility)
            def transcribe_audio():
                return self.whisper_model.transcribe(
                    full_audio_np.astype(np.float32),
                    fp16=torch.cuda.is_available()
                )
            result = await run_in_threadpool(transcribe_audio)
            transcribed_text = result.get("text", "").strip()
            print(f"[DEBUG] Transcript: '{transcribed_text}' (len={len(transcribed_text)})")

            # 3. Always send a response to frontend, even if transcript is empty
            await self.send_status("response", {
                "stt": transcribed_text if transcribed_text else "(No speech detected)",
                "llm": "",
                "tts": "",
                "audio_file": filename
            })

            if not transcribed_text:
                print("[DEBUG] No speech detected or transcription failed.")
                return  # Do not proceed to LLM/TTS if no valid speech

            # 4. Get LLM response (runs in threadpool)
            def process_llm():
                from .llm_service import get_agent, process_llm
                agent = get_agent(self.session_id)
                return process_llm(agent, transcribed_text)
            llm_response = await run_in_threadpool(process_llm)

            # 5. Generate TTS audio (runs in threadpool)
            def generate_tts():
                from .tts_service import process_chatterbox
              # Ensure llm_response is a string
                if isinstance(llm_response, list):
                    text_for_tts = ' '.join(llm_response)
                else:
                    text_for_tts = str(llm_response)
                text_for_tts = text_for_tts.replace('\n', ' ').strip()
                text_for_tts = clean_text_for_tts(text_for_tts)
                return process_api_tts(text_for_tts)
               # return process_chatterbox(text_for_tts)
                
            tts_audio = await run_in_threadpool(generate_tts)

            # 6. Send final response with LLM and TTS to frontend
            await self.send_status("response", {
                "stt": transcribed_text,
                "llm": llm_response,
                "tts": tts_audio,
                "audio_file": filename
            })

            print(f"✅ Response sent [{self.session_id}]")

        except Exception as e:
            print(f"❌ Error [{self.session_id}]: {str(e)[:30]}...")
            await self.send_status("error", {"message": "Processing error"})
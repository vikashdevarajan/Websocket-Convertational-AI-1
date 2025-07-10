import os
from typing import Optional
import base64
from TTS.api import TTS

# Initialize TTS model once (choose your model and device)
TTS_MODEL_NAME = "tts_models/en/ljspeech/speedy-speech"
TTS_DEVICE = "cpu"  # or "cuda" if you have a GPU

class TTSService:
    def __init__(self, model_name=TTS_MODEL_NAME, device=TTS_DEVICE):
        self.tts = TTS(model_name).to(device)

    def text_to_speech(self, text: str, out_path: str = "output.wav") -> str:
        """Converts text to speech and saves to a file."""
        self.tts.tts_to_file(text=text, file_path=out_path)
        return out_path

# Create a global TTS service instance
tts_service = TTSService()

def process_chatterbox(text_input: str) -> str:
    """
    Converts text to speech using a real TTS model and returns base64-encoded audio.
    """
    output_path = "output.wav"
    tts_service.text_to_speech(text_input, out_path=output_path)
    if not os.path.exists(output_path):
        return "(Chatterbox audio not available)"
    with open(output_path, "rb") as f:
        audio_bytes = f.read()
    # Encode audio bytes as base64 string for JSON transport
    return base64.b64encode(audio_bytes).decode("utf-8")
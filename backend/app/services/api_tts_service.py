import requests
import base64
import os

AZURE_TTS_API_KEY = os.getenv("AZURE_TTS_API_KEY") 
AZURE_TTS_URL = "https://vikas-mcxkor0i-eastus2.cognitiveservices.azure.com/openai/deployments/gpt-4o-mini-tts007/audio/speech?api-version=2025-03-01-preview"
#https://vikas-mcxkor0i-eastus2.cognitiveservices.azure.com/openai/deployments/gpt-4o-mini-tts007/audio/speech?api-version=2025-03-01-preview
def process_api_tts(text, voice="alloy", model="gpt-4o-mini-tts007"):
    """
    Sends text to Azure TTS API and returns base64-encoded audio (mp3).
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {AZURE_TTS_API_KEY}"
    }
    payload = {
        "model": model,
        "input": text,
        "voice": voice
    }
    response = requests.post(AZURE_TTS_URL, headers=headers, json=payload)
    if response.status_code == 200:
        # Return base64-encoded audio for frontend compatibility
        return base64.b64encode(response.content).decode("utf-8")
    else:
        print(f"❌ API TTS failed: {response.status_code} {response.text}")
        return ""
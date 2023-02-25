import requests
import os
import uuid

from datetime import datetime

TTS_GENERATION_PATH = "/api/tts"


class TTSClient:
    def __init__(self, config):
        self.url = config["tts"]["host"]

    def generate_tts_audio(self, text, ssml=False):
        # Stick a default voice (without it, it'll jump around for some reason)
        params = {"voice": "en_US/cmu-arctic_low#jmk", "ssml": 1 if ssml else 0}
        response = requests.post(
            self.url + TTS_GENERATION_PATH, params=params, data=text
        )
        dt_string = datetime.now().strftime("%d-%m-%Y_%H")
        file_path = f"audio/{dt_string}/{uuid.uuid4()}.wav"
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "wb") as f:
            f.write(bytes(response.content))
        return file_path

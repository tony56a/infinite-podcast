import requests
import os
import uuid
import base64

from datetime import datetime

TTS_GENERATION_PATH = "/api/tts"


class TTSClient:
    def __init__(self, config):
        self.url = config["tts"]["host"]

    def generate_tts_audio(
        self,
        text,
        ssml=False,
        save_file=False,
        voice="en_US/cmu-arctic_low#jmk",
        name="",
    ):
        # for SSML, stick a default voice (without it, it'll jump around for some reason)
        # for regular situations, set the length scale to 85%
        params = {
            "voice": f"{voice}",
            "ssml": 1 if ssml else 0,
            "lengthScale": 1.1 if ssml else 1.18,
        }
        response = requests.post(
            self.url + TTS_GENERATION_PATH, params=params, data=text
        )

        base64_response = base64.b64encode(bytes(response.content)).decode("ascii")
        if save_file:
            dt_string = datetime.now().strftime("%d-%m-%Y_%H")
            file_path = f"audio/{dt_string}/{uuid.uuid4()}_{name}.wav"
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "wb") as f:
                f.write(bytes(response.content))
            return (file_path, base64_response)
        else:
            return (None, base64_response)

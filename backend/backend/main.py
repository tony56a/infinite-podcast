import constants
import json
import time
from datetime import datetime

from redis_client import RedisClient
from chatgpt_client import ChatGPTClient
from tts_client import TTSClient
from script_generator import generate_files


def fetch_prompt(client):
    prompt = constants.DEFAULT_PROMPT
    return client.generate(prompt)


def extract_text(response):
    return response.replace("```", "")


if __name__ == "__main__":
    with open("config.json", "r") as json_file:
        cfg = json.loads(json_file.read())

    redis_client = RedisClient(config=cfg)
    chatgpt_client = ChatGPTClient(config=cfg)
    tts_client = TTSClient(config=cfg)

    while True:
        length = redis_client.get_length()
        if length < 20:
            try:
                print(f"generating script at {datetime.now()}")
                response = fetch_prompt(client=chatgpt_client)
                result = extract_text(response)
                (animation_sequence, audio_base64, script_metadata) = generate_files(
                    tts_client=tts_client, config=cfg, csv_text=result
                )
                redis_client.push(
                    json.dumps(
                        {
                            "animation": animation_sequence,
                            "audio": audio_base64,
                            "guestGender": script_metadata["guest_gender"],
                        }
                    )
                )
            except Exception as e:
                print(f"generation failed due to {e}")
        time.sleep(30)

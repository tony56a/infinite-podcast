import constants
import json
import time
import argparse
import logging
import random

from logging.handlers import TimedRotatingFileHandler
from datetime import datetime

from redis_client import RedisClient
from chatgpt_client import ChatGPTClient
from tts_client import TTSClient
from script_generator import generate_files

REDIS_SCRIPT_KEY_PREFIX = "backup_script_"

redis_script_key_counter = 0


logger = logging.getLogger()
rotating_file_handler = TimedRotatingFileHandler(
    filename="app.log", when="h", interval=1, backupCount=1
)
formatter = logging.Formatter("%(asctime)s %(name)s:%(levelname)s - %(message)s")
rotating_file_handler.setFormatter(formatter)
logger.addHandler(rotating_file_handler)
logger.setLevel(logging.INFO)

VALID_SCRIPT_TYPES = ["normal", "robot", "skeleton"]
parser = argparse.ArgumentParser(description="Generates podcast scripts")
parser.add_argument(
    "--infinite", help="Keeps generating scripts non-stop", action="store_true"
)
parser.add_argument("--request", help="Grabs the request", action="store_true")
parser.add_argument(
    "--type",
    help="Generate a specifc type of script, only applicable in default mode",
    choices=VALID_SCRIPT_TYPES,
    type=str.lower,
    default="normal",
    required=False,
)


def fetch_prompt(client, script_type, script_prompt):
    prompt_customizations = {
        "normal": ("character", ""),
        "robot": ("robot", " and unrelated to robots, but referencing robots somehow"),
        "skeleton": (
            "skeleton",
            " and unrelated to skeletons, but referencing skeletons somehow",
        ),
    }
    prompt_customization = prompt_customizations[script_type]
    prompt = constants.DEFAULT_PROMPT_TEMPLATE.format(
        host_name=constants.DEFAULT_NAME,
        script_prompt=script_prompt,
        character_type=prompt_customization[0],
        character_addenda=prompt_customization[1],
    )
    return client.generate(prompt)


def extract_text(response):
    return response.replace("```", "")


def do_generate_script(
    cfg,
    chatgpt_client,
    tts_client,
    script_type="normal",
    script_prompt="a random appropriate topic dissimilar from the previous one",
    script_requester=None,
):
    global redis_script_key_counter
    response = fetch_prompt(
        client=chatgpt_client, script_type=script_type, script_prompt=script_prompt
    )
    result = extract_text(response)
    (animation_sequence, audio_base64, script_metadata) = generate_files(
        tts_client=tts_client,
        config=cfg,
        csv_text=result,
        script_type=script_type,
    )
    payload = json.dumps(
        {
            "animation": animation_sequence,
            "audio": audio_base64,
            "guestGender": script_metadata["guest_gender"],
            "guestType": script_type,
        }
    )

    if script_requester:
        redis_client.priority_push(payload)
        request_response_payload = {
            "name": script_requester,
            "prompt": script_prompt,
            "success": True,
        }
        redis_client.push(
            json.dumps(request_response_payload),
            redis_client.script_request_response_queue,
        )
    else:
        redis_client.push(payload)

    backup_script_key = f"{REDIS_SCRIPT_KEY_PREFIX}{redis_script_key_counter}"
    redis_client.add(backup_script_key, payload)
    redis_script_key_counter += 1
    if redis_script_key_counter % 30 == 0:
        redis_script_key_counter = 0


if __name__ == "__main__":
    with open("config.json", "r") as json_file:
        cfg = json.loads(json_file.read())

    redis_client = RedisClient(config=cfg)
    chatgpt_client = ChatGPTClient(config=cfg)
    tts_client = TTSClient(config=cfg)
    args = parser.parse_args()

    if args.infinite:
        while True:
            script_length = redis_client.get_length()

            request = redis_client.get_queue_content(redis_client.script_request_queue)
            try:
                if request:
                    request = json.loads(request)
                    script_prompt = request["prompt"]
                    script_type = request["type"]
                    script_requester = request["name"]
                else:
                    if script_length > 60:
                        logger.info("too many queued scripts already, skipping")
                        time.sleep(50)
                        continue
                    script_prompt = (
                        "a random appropriate topic dissimilar from the previous one"
                    )
                    script_type = "normal"
                    script_requester = None
                    script_random_key_val = random.randint(0, 10)
                    if script_random_key_val == 10:
                        script_type = "skeleton"
                    elif script_random_key_val == 0:
                        script_type = "robot"
                logger.info(f"generating script", extra={"timestamp": datetime.now()})
                do_generate_script(
                    cfg,
                    chatgpt_client,
                    tts_client,
                    script_type=script_type,
                    script_prompt=script_prompt,
                    script_requester=script_requester,
                )
                logger.info(
                    f"completed generation of script",
                    extra={"timestamp": datetime.now()},
                )
            except Exception as e:
                logger.error(f"generation failed due to {e}")
                if request:
                    request_response_payload = {
                        "name": script_requester,
                        "prompt": script_prompt,
                        "success": False,
                    }
                    redis_client.push(
                        json.dumps(request_response_payload),
                        redis_client.script_request_response_queue,
                    )

                if script_length < 10:
                    # If errored out and scripts are running low, pull a random backup script and load it
                    keys = redis_client.get_keys(f"{REDIS_SCRIPT_KEY_PREFIX}*")[1]
                    key = random.choice(keys)
                    redis_client.push(redis_client.get(key))
                    # Since this takes less time then chatGPT, sleep for a bit longer so we don't buffer too many
                    # backups
                    time.sleep(10)

            time.sleep(50)
    elif args.request:
        request = redis_client.get_queue_content(redis_client.script_request_queue)
        if not request:
            logger.warning("No request found, returning")
        else:
            request = json.loads(request)
            script_prompt = request["prompt"]
            script_type = request["type"]
            script_requester = request["name"]
            try:
                do_generate_script(
                    cfg,
                    chatgpt_client,
                    tts_client,
                    script_type=script_type,
                    script_prompt=script_prompt,
                    script_requester=script_requester,
                )
            except Exception as e:
                logger.error(f"generation failed due to {e}")
                request_response_payload = {
                    "name": script_requester,
                    "prompt": script_prompt,
                    "success": False,
                }
                redis_client.push(
                    json.dumps(request_response_payload),
                    redis_client.script_request_response_queue,
                )
    else:
        logger.info(f"generating script", extra={"timestamp": datetime.now()})
        do_generate_script(cfg, chatgpt_client, tts_client, args.type)

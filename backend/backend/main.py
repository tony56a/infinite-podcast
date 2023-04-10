import constants
import json
import time
import argparse
import logging
import random

from logging.handlers import TimedRotatingFileHandler
from datetime import datetime
from openai import error

from redis_client import RedisClient
from chatgpt_client import ChatGPTClient
from tts_client import TTSClient
from script_generator import generate_files
from utils import generate_requested_script, prompt_customizations


redis_script_key_counter = 0


logger = logging.getLogger()
rotating_file_handler = TimedRotatingFileHandler(
    filename="app.log", when="h", interval=6, backupCount=4
)
formatter = logging.Formatter("%(asctime)s %(name)s:%(levelname)s - %(message)s")
rotating_file_handler.setFormatter(formatter)
logger.addHandler(rotating_file_handler)
logger.setLevel(logging.INFO)

parser = argparse.ArgumentParser(description="Generates podcast scripts")
parser.add_argument(
    "--infinite", help="Keeps generating scripts non-stop", action="store_true"
)
parser.add_argument(
    "--test-request",
    help="generates a manual request with a test name and the provided prompt",
)
parser.add_argument(
    "--test-rap-battle-request",
    help="generates a manual rap battle request with a test name and the provided prompt",
)
parser.add_argument(
    "--test-business-talk-request",
    help="generates a manual business talk request with a test name and the provided prompt",
)
parser.add_argument("--request", help="Grabs the request", action="store_true")
parser.add_argument(
    "--type",
    help="Generate a specifc type of script, only applicable in default mode",
    choices=constants.VALID_SCRIPT_TYPES,
    type=str.lower,
    default="normal",
    required=False,
)


def fetch_prompt(
    client,
    guest_type,
    script_prompt,
    script_requester,
    guest_personality=("", ""),
    scene_type="podcast",
):
    prompt_customization = prompt_customizations[guest_type]
    prompt = constants.DEFAULT_PROMPT_TEMPLATE.format(
        host_name=constants.DEFAULT_NAME,
        script_prompt=script_prompt,
        character_type=prompt_customization[0],
        character_addenda=prompt_customization[1],
        character_prefix=guest_personality[0],
        character_postfix=guest_personality[1],
    )

    response = None
    if script_requester:
        # If this is a manual request, then get an entry from the real API first
        try:
            api_prompt = generate_requested_script(
                prompt_customization=prompt_customization,
                script_prompt=script_prompt,
                scene_type=scene_type,
            )
            logger.info(f"Generating direct OpenAI script for {api_prompt}")
            response = client.generate_real_openapi(api_prompt)
        except Exception as e:
            logger.exception(f"direct OpenAI generation failed due to {e}")
            response = None

    return response or client.generate(prompt)


def do_generate_script(
    cfg,
    chatgpt_client,
    tts_client,
    guest_type="normal",
    script_prompt=constants.DEFAULT_PROMPT_DISCUSSION_TOPIC,
    script_requester=None,
    script_personality=None,
    scene_type="podcast",
):
    global redis_script_key_counter

    response = fetch_prompt(
        client=chatgpt_client,
        guest_type=guest_type,
        script_prompt=script_prompt,
        script_requester=script_requester,
        guest_personality=script_personality,
        scene_type=scene_type,
    )
    (animation_sequence, audio_base64, script_metadata) = generate_files(
        tts_client=tts_client,
        config=cfg,
        csv_text=response,
        guest_type=guest_type,
        scene_type=scene_type,
    )
    payload = json.dumps(
        {
            "animation": animation_sequence,
            "audio": audio_base64,
            "guestGender": script_metadata["guest_gender"],
            "guestType": guest_type,
            "prompt": script_prompt,
            "requester": script_requester,
            "sceneType": scene_type,
        }
    )

    if script_requester:
        # If there's a requester, then we need to publish the result to twitch,
        # and push into requested queue instead of the normal queue
        redis_client.push(payload, queue=redis_client.requested_script_queue)
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

    backup_script_key = f"{constants.REDIS_SCRIPT_KEY_PREFIX}{redis_script_key_counter}"
    redis_client.add(backup_script_key, payload)
    redis_script_key_counter += 1
    if redis_script_key_counter % 30 == 0:
        redis_script_key_counter = 0


def do_push_backup_script(script_length, redis_client):
    if script_length < 10:
        # If errored out and scripts are running low, pull a random backup script and load it
        keys = redis_client.get_keys(f"{constants.REDIS_SCRIPT_KEY_PREFIX}*")[1]
        key = random.choice(keys)
        redis_client.push(redis_client.get(key))
        # Since this takes less time then chatGPT, sleep for a bit longer so we don't buffer too many
        # backups
        time.sleep(10)


if __name__ == "__main__":
    with open("config.json", "r") as json_file:
        cfg = json.loads(json_file.read())

    redis_client = RedisClient(config=cfg)
    chatgpt_client = ChatGPTClient(config=cfg)
    tts_client = TTSClient(config=cfg)
    args = parser.parse_args()

    if args.infinite:
        potential_auto_topics = [
            constants.DEFAULT_HUMEROUS_PROMPT_DISCUSSION_TOPIC,
            constants.DEFAULT_PROMPT_DISCUSSION_TOPIC,
        ]

        while True:
            script_length = redis_client.get_length()

            request = redis_client.get_queue_content(redis_client.script_request_queue)
            if not request and script_length > 60:
                logger.debug("too many queued scripts already, skipping")
                time.sleep(5)
                continue
            try:
                if request:
                    request = json.loads(request)
                    script_prompt = request["prompt"]
                    script_type = request["type"]
                    script_requester = request["name"]
                    scene_type = request["scene_type"]
                    logger.info(
                        f"Generating requested {script_type} script with prompt {script_prompt}"
                    )
                else:
                    if random.randint(0, 10) == 10:
                        script_prompt = (
                            constants.DEFAULT_GUEST_HOST_COMBATIVE_PROMPT_DISCUSSION_TOPIC
                        )
                    else:
                        script_prompt = random.choice(potential_auto_topics)
                    script_type = "normal"
                    script_requester = None
                    script_random_key_val = random.randint(0, 10)
                    if script_random_key_val == 10:
                        script_type = "skeleton"
                    elif script_random_key_val == 0:
                        script_type = "robot"
                    scene_type = "podcast"
                logger.info(f"generating script", extra={"timestamp": datetime.now()})
                script_guest_personality = (
                    "",
                    "",
                )  # random.choice(constants.RANDOM_GUEST_PERSONALITIES)
                do_generate_script(
                    cfg,
                    chatgpt_client,
                    tts_client,
                    guest_type=script_type,
                    script_prompt=script_prompt,
                    script_requester=script_requester,
                    script_personality=script_guest_personality,
                    scene_type=scene_type,
                )
                logger.info(
                    f"completed generation of script",
                    extra={"timestamp": datetime.now()},
                )
            except Exception as error:
                logger.exception(f"generation failed due to error {error}")
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
                do_push_backup_script(
                    script_length=script_length, redis_client=redis_client
                )

            time.sleep(20)
    elif args.test_request:
        script_prompt = args.test_request
        script_type = args.type
        script_requester = "test"
        do_generate_script(
            cfg,
            chatgpt_client,
            tts_client,
            guest_type=script_type,
            script_prompt=script_prompt,
            script_requester=script_requester,
            script_personality=random.choice(constants.RANDOM_GUEST_PERSONALITIES),
        )
    elif args.test_rap_battle_request:
        script_prompt = args.test_rap_battle_request
        script_type = args.type
        script_requester = "test"
        do_generate_script(
            cfg,
            chatgpt_client,
            tts_client,
            guest_type=script_type,
            script_prompt=script_prompt,
            script_requester=script_requester,
            script_personality=random.choice(constants.RANDOM_GUEST_PERSONALITIES),
            scene_type="rapbattle",
        )
    elif args.test_business_talk_request:
        script_prompt = args.test_business_talk_request
        script_type = args.type
        script_requester = "test"
        do_generate_script(
            cfg,
            chatgpt_client,
            tts_client,
            guest_type=script_type,
            script_prompt=script_prompt,
            script_requester=script_requester,
            script_personality=random.choice(constants.RANDOM_GUEST_PERSONALITIES),
            scene_type="businesstalk",
        )
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
                    guest_type=script_type,
                    script_prompt=script_prompt,
                    script_requester=script_requester,
                    script_personality=random.choice(
                        constants.RANDOM_GUEST_PERSONALITIES
                    ),
                )
            except Exception as error:
                logger.error(f"generation failed due to {error}")
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
        do_generate_script(
            cfg,
            chatgpt_client,
            tts_client,
            args.type,
            script_personality=random.choice(constants.RANDOM_GUEST_PERSONALITIES),
        )

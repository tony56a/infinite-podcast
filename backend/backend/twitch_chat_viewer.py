import constants

from twitchAPI import Twitch
from twitchAPI.oauth import UserAuthenticator
from twitchAPI.types import AuthScope, ChatEvent
from twitchAPI.chat import Chat, EventData, ChatCommand
from ratelimit import limits, RateLimitException
from logging.handlers import TimedRotatingFileHandler

from redis_client import RedisClient
from chatgpt_client import ChatGPTClient
from utils import generate_requested_script, prompt_customizations

import json
import logging
import time
import asyncio

USER_SCOPE = [AuthScope.CHAT_READ, AuthScope.CHAT_EDIT]
TARGET_CHANNEL = "podcastsforever"

logger = logging.getLogger()
rotating_file_handler = TimedRotatingFileHandler(
    filename="chatbot.log", when="h", interval=6, backupCount=4
)
formatter = logging.Formatter("%(asctime)s %(name)s:%(levelname)s - %(message)s")
rotating_file_handler.setFormatter(formatter)
logger.addHandler(rotating_file_handler)
logger.setLevel(logging.INFO)

redis_client = None
chatgpt_client = None
approved_users = set()


# this will be called when the event READY is triggered, which will be on bot start
async def on_ready(ready_event: EventData):
    print("Bot is ready for work, joining channels")
    # join our target channel, if you want to join multiple, either call join for each individually
    # or even better pass a list of channels as the argument
    await ready_event.chat.join_room(TARGET_CHANNEL)
    # you can do other bot initialization things in here


@limits(calls=3, period=20)
def check_api_limit():
    return


@limits(calls=20, period=20)
def check_queue_limit():
    return


async def generate_rapbattle_script_request(cmd: ChatCommand):
    global redis_client

    if len(cmd.parameter) == 0:
        logger.error("No params available")
        return

    payload = None
    try:
        payload = do_generate_prompt_request(cmd, scene_type="rapbattle")
    except RateLimitException as e:
        await cmd.reply(f"Sorry {cmd.user.name}, try again in another minute")
        return

    redis_client.push(
        payload=json.dumps(payload), queue=redis_client.script_request_queue
    )

    prompt = payload["prompt"]
    truncated_str = (prompt[:250] + "..") if len(prompt) > 250 else prompt
    await cmd.reply(
        f'OK {cmd.user.name}, queuing up a {payload["type"]} rap battle with the prompt "{truncated_str}"'
    )


async def generate_businesstalk_script_request(cmd: ChatCommand):
    global redis_client

    payload = None
    try:
        prompt = cmd.parameter or "a ridiculous and absurd random topic"

        if not cmd.user.mod and cmd.user.name.lower() not in approved_users:
            check_api_limit()

        payload = {
            "name": cmd.user.name,
            "type": "normal",
            "prompt": prompt,
            "scene_type": "businesstalk",
        }
    except RateLimitException as e:
        await cmd.reply(f"Sorry {cmd.user.name}, try again in another minute")
        return

    redis_client.push(
        payload=json.dumps(payload), queue=redis_client.script_request_queue
    )

    prompt = payload["prompt"]
    truncated_str = (prompt[:250] + "..") if len(prompt) > 250 else prompt
    await cmd.reply(
        f'OK {cmd.user.name}, queuing up a business talk with the prompt "{truncated_str}"'
    )


# this will be called whenever the !reply command is issued
async def generate_script_request(cmd: ChatCommand):
    global redis_client

    if len(cmd.parameter) == 0:
        logger.error("No params available")
        return

    payload = do_generate_prompt_request(cmd, scene_type="podcast")

    redis_client.push(
        payload=json.dumps(payload), queue=redis_client.script_request_queue
    )

    prompt = payload["prompt"]
    truncated_str = (prompt[:250] + "..") if len(prompt) > 250 else prompt
    await cmd.reply(
        f'OK {cmd.user.name}, queuing up a {payload["type"]} script with the prompt "{truncated_str}"'
    )


def do_generate_prompt_request(cmd: ChatCommand, scene_type: str):
    commands = cmd.parameter.split(" ")
    type = commands[0].lower()
    prompt = " ".join(commands[1:]).strip() or "a ridiculous and absurd random topic"

    # TODO: extract validation to seperate function
    if type not in constants.VALID_SCRIPT_TYPES:
        prompt = " ".join(commands).strip()
        type = "normal"

    if not cmd.user.mod and cmd.user.name.lower() not in approved_users:
        check_api_limit()

    payload = {
        "name": cmd.user.name,
        "type": type,
        "prompt": prompt,
        "scene_type": scene_type,
    }
    return payload


async def get_next_topics(cmd: ChatCommand):
    try:
        check_queue_limit()
    except RateLimitException as e:
        await cmd.reply(f"Sorry {cmd.user.name}, try again later")
        return

    entries = [
        json.loads(script)
        for script in redis_client.read_next_entries(
            redis_client.requested_script_queue
        )
    ]

    in_progress_prompts = [
        json.loads(script)
        for script in redis_client.read_next_entries(redis_client.script_request_queue)
    ]

    prefix = "Upcoming Prompts:\n"
    entries = [
        f"{entry['requester']}: {entry['prompt'][:100]}{'...' if len(entry['prompt']) > 100 else ''}"
        for entry in entries
    ]
    entries.reverse()
    result = "  ".join(entries)
    await cmd.send(prefix + result)

    in_progress_prompts_prefix = "Generating Prompts:\n\n"
    entries = [
        f"{entry['name']}: {entry['prompt'][:100]}{'...' if len(entry['prompt']) > 100 else ''}"
        for entry in in_progress_prompts
    ]
    entries.reverse()
    result = "\n\n".join(entries)
    await cmd.send(in_progress_prompts_prefix + result)

    return


async def run():
    global redis_client, chatgpt_client, approved_users
    with open("config.json", "r") as json_file:
        cfg = json.loads(json_file.read())

    app_id = cfg["chatbot"]["client_id"]
    app_secret = cfg["chatbot"]["client_secret"]
    approved_users = cfg["chatbot"]["approved_users"]
    redis_client = RedisClient(config=cfg)
    chatgpt_client = ChatGPTClient(config=cfg)

    # set up twitch api instance and add user authentication with some scopes
    twitch = await Twitch(app_id, app_secret)
    auth = UserAuthenticator(twitch, USER_SCOPE)
    token, refresh_token = await auth.authenticate()
    await twitch.set_user_authentication(token, USER_SCOPE, refresh_token)

    # create chat instance
    chat = await Chat(twitch)

    # you can directly register commands and their handlers, this will register the !reply command
    chat.register_event(ChatEvent.READY, on_ready)
    chat.register_command("script", generate_script_request)
    chat.register_command("prompt", generate_script_request)
    chat.register_command("rapbattle", generate_rapbattle_script_request)
    chat.register_command("businesstalk", generate_businesstalk_script_request)
    chat.register_command("queue", get_next_topics)

    chat.start()

    # lets run till we press enter in the console
    try:
        while True:
            raw_response_payload = redis_client.get_queue_content(
                redis_client.script_request_response_queue
            )
            if raw_response_payload:
                response_payload = json.loads(raw_response_payload)
                logger.info(response_payload)
                if response_payload["success"]:
                    status_string = "successful!"
                else:
                    status_string = "unsuccessful :("
                try:
                    prompt = response_payload["prompt"]
                    truncated_str = (
                        (prompt[:250] + "..") if len(prompt) > 250 else prompt
                    )
                    await chat.send_message(
                        TARGET_CHANNEL,
                        f"{response_payload['name']}, Prompt: \"{truncated_str}\" was {status_string}",
                    )
                except Exception:
                    pass
            time.sleep(5)
    finally:
        # now we can close the chat bot and the twitch api client
        chat.stop()
        await twitch.close()


if __name__ == "__main__":
    asyncio.run(run())

from twitchAPI import Twitch
from twitchAPI.oauth import UserAuthenticator
from twitchAPI.types import AuthScope, ChatEvent
from twitchAPI.chat import Chat, EventData, ChatCommand
from redis_client import RedisClient
from logging.handlers import TimedRotatingFileHandler

import json
import logging
import time
import asyncio

USER_SCOPE = [AuthScope.CHAT_READ, AuthScope.CHAT_EDIT]
TARGET_CHANNEL = "podcastsforever"

logger = logging.getLogger()
rotating_file_handler = TimedRotatingFileHandler(
    filename="chatbot.log", when="h", interval=1, backupCount=1
)
formatter = logging.Formatter("%(asctime)s %(name)s:%(levelname)s - %(message)s")
rotating_file_handler.setFormatter(formatter)
logger.addHandler(rotating_file_handler)
logger.setLevel(logging.INFO)

redis_client = None
approved_users = set()


# this will be called when the event READY is triggered, which will be on bot start
async def on_ready(ready_event: EventData):
    print("Bot is ready for work, joining channels")
    # join our target channel, if you want to join multiple, either call join for each individually
    # or even better pass a list of channels as the argument
    await ready_event.chat.join_room(TARGET_CHANNEL)
    # you can do other bot initialization things in here


# this will be called whenever the !reply command is issued
async def generate_script_request(cmd: ChatCommand):
    global redis_client

    if len(cmd.parameter) == 0:
        logger.error("No params available")
        return
    else:
        if not cmd.user.mod and cmd.user.name.lower() not in approved_users:
            logger.warning("Not a mod, cannot run")
            await cmd.reply(f"Sorry {cmd.user.name}, but you can't queue scripts")
        else:
            commands = cmd.parameter.split(" ")
            type = commands[0].lower()
            prompt = " ".join(commands[1:]).strip()
            payload = {
                "name": cmd.user.name,
                "type": type,
                "prompt": prompt,
            }
            redis_client.push(
                payload=json.dumps(payload), queue=redis_client.script_request_queue
            )
            await cmd.reply(
                f'OK {cmd.user.name}, queuing up a {type} script with the prompt "{prompt}"'
            )


async def run():
    global redis_client, approved_users
    with open("config.json", "r") as json_file:
        cfg = json.loads(json_file.read())

    app_id = cfg["chatbot"]["client_id"]
    app_secret = cfg["chatbot"]["client_secret"]
    approved_users = cfg["chatbot"]["approved_users"]
    redis_client = RedisClient(config=cfg)

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

    # we are done with our setup, lets start this bot up!
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
                await chat.send_message(
                    TARGET_CHANNEL,
                    f"{response_payload['name']}, Prompt: \"{response_payload['prompt']}\" was {'successful!' if response_payload['success'] else 'not successful :('}",
                )
            time.sleep(5)
    finally:
        # now we can close the chat bot and the twitch api client
        chat.stop()
        await twitch.close()


if __name__ == "__main__":
    asyncio.run(run())

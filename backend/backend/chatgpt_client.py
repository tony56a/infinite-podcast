import logging
import datetime
import re
import openai as openaiAPI
import constants

from revChatGPT.V1 import Chatbot

logger = logging.getLogger()


class ChatGPTClient:
    def _trim_response(self, response):
        beginning_regex = r"^(.*)```.*\"?\s*name\s*\"?,\s*\"?gender\s*\"?,"
        end_regex = r"```(.*)$"
        front_trimmed_response = re.sub(
            beginning_regex,
            "Name,Gender,",
            response,
            1,
            re.DOTALL | re.MULTILINE | re.IGNORECASE,
        )
        back_trimmed_response = re.sub(
            end_regex,
            "",
            front_trimmed_response,
            1,
            re.DOTALL | re.MULTILINE | re.IGNORECASE,
        )
        return back_trimmed_response

    def __init__(self, config):
        self.request_count = 0
        self.previous_convo_id = config["chatgpt"].get("previous_prompt")
        self.chatbot = Chatbot(
            {"access_token": config["chatgpt"]["access_token"]},
            conversation_id=config["chatgpt"].get("previous_prompt"),
        )
        openaiAPI.api_key = config["chatgpt"]["api_access_token"]

    def generate(self, prompt):
        bad_responses = [
            "As a large language model trained by OpenAI,",
            "As a language model trained by OpenAI,",
            "I'm sorry, ",
            "I apologize",
        ]

        api_response = None

        for data in self.chatbot.ask(prompt, timeout=360):
            api_response = data

        parsed_response = self._trim_response(api_response["message"].lower().strip())

        for bad_response in bad_responses:
            if bad_response in parsed_response:
                logging.warn("bad response, regenerating")
                for data in self.chatbot.ask(
                    prompt,
                    timeout=360,
                    conversation_id=api_response["conversation_id"],
                    parent_id=api_response["parent_id"],
                ):
                    api_response = data

        self.request_count += 1
        if self.request_count % 50 == 0:
            logging.warn("resetting convo")
            self.reset_convo()
        return self._trim_response(api_response["message"].lower().strip())

    def generate_real_openapi(self, prompt):
        completion = openaiAPI.ChatCompletion.create(
            model="gpt-3.5-turbo",
            temperature=0.8,
            presence_penalty=0.25,
            frequency_penalty=0.25,
            messages=[
                {
                    "role": "system",
                    "content": constants.DEFAULT_API_COMMAND_CONFIG_PROMPT,
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
        )
        return completion["choices"][0]["message"]["content"].lower().strip()

    def reset_convo(self):
        self.chatbot.conversation_id = None
        self.chatbot.parent_id = None

import logging
import re
import openai as openaiAPI
import constants
import csv
import unidecode

from better_profanity import profanity
from retry import retry
from io import StringIO
from poe import (
    load_chat_id_map,
    clear_context,
    send_message,
    get_latest_message,
    set_auth,
)

logger = logging.getLogger()


class ChatGPTClient:
    def _trim_response(self, response):
        logger.info(f"raw chatgpt response: {response}")
        beginning_regex = r"^(.*)```.*\"?\s*name\s*\"?,\s*\"?gender\s*\"?,"
        end_regex = r"```(.*)$"
        front_trimmed_response = re.sub(
            beginning_regex,
            "Name|Gender|",
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
        split_lines = [
            line for line in back_trimmed_response.split("\n") if line.strip() != ""
        ]
        title_line = split_lines[0].lower()
        if "gender" not in title_line or "name" not in title_line:
            split_lines = ["name|gender|text"] + split_lines
        # we can't trust chatGPT output here, so replace entirely
        split_lines[0] = "name|gender|text"

        updated_lines = []
        build_up_line = ""
        for line in split_lines:
            if not line:
                continue
            if line.count("|") == 2:
                if build_up_line:
                    updated_lines.append(build_up_line)
                build_up_line = line
            else:
                build_up_line += f" {line}"
        if build_up_line:
            updated_lines.append(build_up_line)

        split_lines = [
            line
            for line in updated_lines
            if line.count("|") >= 2 and line.count("-|") < 2
        ]

        newline_trimmed_response = (
            "\n".join(split_lines).replace("\\n", "\n").replace("\\t", "\t")
        )

        f = StringIO(unidecode.unidecode(newline_trimmed_response))
        reader = csv.DictReader(
            f, delimiter="|", skipinitialspace=True, quoting=csv.QUOTE_NONE
        )
        script_components = [line for line in reader]
        if len(script_components) <= 0:
            raise RuntimeError("script components will be empty")

        return newline_trimmed_response

    def __init__(self, config, should_reset=True):
        profanity.load_censor_words()
        self.request_count = 0
        self.previous_convo_id = config["chatgpt"].get("previous_prompt")

        set_auth("Quora-Formkey", config["poe"]["form_key"])
        set_auth("Cookie", config["poe"]["cookie"])

        openaiAPI.api_key = config["chatgpt"]["api_access_token"]
        self.bot = "chinchilla"
        self.chat_id = load_chat_id_map(self.bot)
        if should_reset:
            self.reset_convo()

    def generate(self, prompt):
        logger.info(f"submitting the following prompt: {prompt}")
        api_response = None

        send_message(prompt, self.bot, self.chat_id)
        api_response = get_latest_message(self.bot)

        parsed_response = None
        try:
            parsed_response = self._trim_response(api_response.strip())
        except Exception:
            logging.exception("error whilst processing output, resetting")
            self.reset_convo()

        self.request_count += 1
        if self.request_count % 5 == 0:
            logging.warn("resetting convo")
            self.reset_convo()

        return parsed_response

    @retry(RuntimeError, tries=3, delay=2)
    def generate_real_openapi(self, prompt, insert_system_prompt=False):
        request = []
        if insert_system_prompt:
            request.append(
                {
                    "role": "system",
                    "content": constants.DEFAULT_API_COMMAND_CONFIG_PROMPT,
                }
            )
        if type(prompt) is list:
            for prompt_str in prompt:
                request.append(
                    {
                        "role": "user",
                        "content": prompt_str,
                    }
                )
        else:
            request.append(
                {
                    "role": "user",
                    "content": prompt,
                }
            )
        completion = openaiAPI.ChatCompletion.create(
            model="gpt-4",
            temperature=0.8,
            presence_penalty=0,
            frequency_penalty=0.6,
            messages=request,
            request_timeout=150,
        )
        raw_response = self._trim_response(
            completion["choices"][0]["message"]["content"].strip()
        )

        return profanity.censor(
            raw_response.replace('"', "~").replace("'", "~"), "A"
        ).replace("~", "'")

    def moderate(self, prompt):
        result = openaiAPI.Moderation.create(input=prompt)
        return result["results"][0]

    def reset_convo(self):
        if self.chat_id:
            clear_context(self.chat_id)

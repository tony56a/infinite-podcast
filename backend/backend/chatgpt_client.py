import logging
import re
import constants
import csv
import unidecode
import requests

from retry import retry
from io import StringIO
from openai import OpenAI

logger = logging.getLogger()


class ChatGPTClient:

    def __init__(self, config):
        self.local_llama_host_url = config["local-llama"]["host"]
        self.openAIclient = OpenAI(api_key=config["chatgpt"]["api_access_token"])

    def _trim_response(self, response):
        logger.info(f"raw chatgpt response: {response}")
        beginning_regex = r"^(.*)```.*\"?\s*name\s*\"?,\s*\"?gender\s*\"?,"
        end_regex = r"```(.*)$"
        title_line_regex = r"\|\s*-*\s*\|\s*-*\s*\|\s*-*\s*\|"
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
            line
            for line in back_trimmed_response.split("\n")
            if line.strip() != "" and not re.findall(title_line_regex, line)
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
            if line.count("|") >= 2:
                if build_up_line:
                    updated_lines.append(build_up_line)
                build_up_line = line
            else:
                build_up_line += f" {line}"
        if build_up_line:
            updated_lines.append(build_up_line)

        split_lines = [
            line.rstrip("|").lstrip("|")
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

    def generate(self, prompt):
        logger.info(f"submitting the following prompt: {prompt}")
        api_response = None
        # text-generation-ui has API server similar to OpenAI
        request = self._generate_request_payload(prompt, insert_system_prompt=False)
        payload = {
            "mode": "instruct",
            "stream": False,
            "messages": request,
            "max_tokens": 2048,
        }

        parsed_response = None
        try:
            api_response = (
                requests.post(
                    self.local_llama_host_url + "/v1/chat/completions",
                    headers={"Content-Type": "application/json"},
                    json=payload,
                    verify=False,
                )
                .json()["choices"][0]["message"]["content"]
                .strip()
            )
            # Do some trimming on the LLAMA specific response, then do general trimming
            # TODO: Make this trimming service/model agnostic
            parsed_response = self._trim_response(
                self._trim_llama_response(api_response)
            )
        except Exception:
            logging.exception("error whilst processing output, resetting")

        return parsed_response

    @retry(RuntimeError, tries=3, delay=2)
    def generate_real_openapi(self, prompt, insert_system_prompt=False):
        request = self._generate_request_payload(prompt, insert_system_prompt)
        completion = self.openAIclient.chat.completions.create(
            model="gpt-4-1106-preview",
            temperature=0.8,
            presence_penalty=0,
            frequency_penalty=0.6,
            messages=request,
        )
        raw_response = self._trim_response(
            completion.choices[0].message.content.strip()
        )

        return raw_response

    def _generate_request_payload(self, prompt, insert_system_prompt):
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
        return request

    def _trim_llama_response(self, response):
        split_lines = response.split("\n")
        # Trim off fist lines until header
        # (local model, so reasonable assurance that results are reproducable)
        for i in range(len(split_lines)):
            trimmed_line = [c.strip() for c in split_lines[0].lower().split("|") if c]
            if "name" in trimmed_line and "gender" in trimmed_line:
                break
            else:
                split_lines = split_lines[1:]

        split_lines = [line for line in split_lines if line.count("-") < 5]

        # Remove last line if not a valid CSV line
        try:
            if split_lines[-1].count("|") < 2:
                split_lines = split_lines[:-1]
        except Exception as e:
            logger.exception(f"Cannot parse result, lines were {split_lines}")

        return "\n".join(split_lines)

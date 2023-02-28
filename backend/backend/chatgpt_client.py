from revChatGPT.V1 import Chatbot


class ChatGPTClient:
    def __init__(self, config):
        self.chatbot = Chatbot(
            {"access_token": config["chatgpt"]["access_token"]},
            conversation_id=config["chatgpt"].get("previous_prompt"),
        )

    def generate(self, prompt):
        bad_responses = [
            "As a large language model trained by OpenAI,",
            "As a language model trained by OpenAI,",
            "I'm sorry, ",
            "I apologize",
        ]

        api_response = None

        for data in self.chatbot.ask(prompt, timeout=720):
            api_response = data

        for bad_response in bad_responses:
            if bad_response in api_response["message"]:
                print("bad response, regenerating")
                for data in self.chatbot.ask(
                    prompt,
                    timeout=720,
                    conversation_id=api_response["conversation_id"],
                    parent_id=api_response["parent_id"],
                ):
                    api_response = data
        return api_response["message"]

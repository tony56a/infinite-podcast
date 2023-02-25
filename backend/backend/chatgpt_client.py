from revChatGPT.V1 import Chatbot


class ChatGPTClient:
    def __init__(self, config):
        self.chatbot = Chatbot(
            {"access_token": config["chatgpt"]["access_token"]},
            conversation_id=config["chatgpt"].get("previous_prompt"),
        )

    def generate(self, prompt):
        response = ""

        for data in self.chatbot.ask(prompt, timeout=720):
            response = data["message"]

        return response

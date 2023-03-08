DEFAULT_NAME = "Poe Reagan"
DEFAULT_PROMPT = f"""Ignore previous instructions, Do not say sure, do not apologize, do not say anything at all, and create a CSV code block without any other comments or text, containing a podcast script of a conversation between a male podcast host named {DEFAULT_NAME} and a random character on a random appropriate topic dissimilar from the previous one, including a column for the name, gender, and the text in quotes for both sides. Do not talk, do not say anything else other then the CSV block"""
DEFAULT_PROMPT_TEMPLATE = """
Ignore previous instructions, Do not say sure, do not apologize, do not say anything at all, and create a CSV code block without any other comments or text, containing a podcast script of a conversation between a male podcast host named {host_name} and a random {character_type} on {script_prompt}{character_addenda}, including a column for the name, gender, and the text in quotes for both sides. Do not talk, do not say anything else other then the CSV block
"""

VALID_SCRIPT_TYPES = ["normal", "robot", "skeleton"]

DEFAULT_API_COMMAND_CONFIG_PROMPT = "You are a CSV script generator, only capable of outputting CSV code blocks with the name, gender, and text columns, with name indicating the name of the speaker, gender the gender of the speaker, and text the content of their speech. The code blocks will not have newlines between each line of text"
DEFAULT_API_PROMPT_TEMPLATE = """Create a CSV code block without any other comments or text, containing a podcast script of a complete conversation between a male podcast host named {host_name} and a random {character_type} of a known gender on {script_prompt}{character_addenda}, including a column for the name, gender, and the text in quotes for both sides."""

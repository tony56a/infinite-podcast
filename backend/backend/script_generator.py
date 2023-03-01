import csv
import constants
import concurrent.futures
import time
import unidecode

from functools import partial
from io import StringIO
from ssml_builder.core import Speech


def build_script_ssml(config, script_components):
    voices = {
        "host": f"en_US/{config['tts']['host_voice']}",
        "male": f"en_US/{config['tts']['male_voice']}",
        "female": f"en_US/{config['tts']['female_voice']}",
    }
    speech = Speech()
    # add mimic3 voices to generator
    speech.VALID_VOICE_NAMES = tuple(voices.values())

    script_speech = []
    for script_component in script_components:
        text = (
            script_component.get("text")
            or script_component.get("dialogue")
            or script_component.get("transcript")
        )
        is_host = constants.DEFAULT_NAME.lower() in script_component["name"]
        if is_host:
            voice = voices["host"]
        else:
            if (
                script_component["gender"] == "m"
                or script_component["gender"] == "male"
            ):
                voice = voices["male"]
            else:
                voice = voices["female"]

        speech_block = f"""
        <s>
            {speech.voice(value=text, name=voice, is_nested = True)}
            {speech.pause(time="0.3s", is_nested = True)}
        </s>
        """
        script_speech.append(speech_block)
    return speech.prosody(
        value="".join(script_speech).replace("\n", ""), rate="85%"
    ).speak()


def syllable_count(word):
    word = word.lower()
    count = 0
    vowels = "aeiouy"
    if word[0] in vowels:
        count += 1
    for index in range(1, len(word)):
        if word[index] in vowels and word[index - 1] not in vowels:
            count += 1
    if word.endswith("e"):
        count -= 1
    if count == 0:
        count += 1
    return count


def build_script_client_calls(config, script_components, tts_client, save_file=False):
    voices = {
        "host": f"en_US/{config['tts']['host_voice']}",
        "male": f"en_US/{config['tts']['male_voice']}",
        "female": f"en_US/{config['tts']['female_voice']}",
    }

    client_calls = []
    for script_component in script_components:
        text = (
            script_component.get("text")
            or script_component.get("dialogue")
            or script_component.get("transcript")
        )
        is_host = (
            constants.DEFAULT_NAME.lower() in script_component["name"]
            or "poe" in script_component["name"]
        )
        if is_host:
            voice = voices["host"]
        else:
            if (
                script_component["gender"] == "m"
                or script_component["gender"] == "male"
            ):
                voice = voices["male"]
            else:
                voice = voices["female"]
        client_calls.append(
            partial(
                tts_client.generate_tts_audio,
                text=text,
                voice=voice,
                save_file=save_file,
            )
        )

    return client_calls


def get_script_component_text(components, index):
    return (
        components[index].get("text")
        or components[index].get("dialogue")
        or components[index].get("transcript")
    )


def generate_animation_file(script_components):
    ratios = {
        "host": 0.2264,
        "male": 0.2345,
        "female": 0.2345,
    }
    animation_file = []

    for script_component in script_components[:-1]:
        is_host = (
            constants.DEFAULT_NAME.lower() in script_component["name"]
            or "poe" in script_component["name"]
        )
        if is_host:
            camera = 1
            character_pose = [1, 0]
        else:
            camera = 2
            character_pose = [0, 1]

        animation_file.append(
            {
                "camera": camera,
                "characterPose": character_pose,
                # This used to be a real value, stub in one and retrieve from files instead
                "length": 1,
            }
        )

    text = get_script_component_text(script_components, -1)
    animation_file.append(
        {
            "camera": 0,
            "characterPose": [0, 0],
            "length": 1,
        }
    )
    return animation_file


def generate_files(tts_client, config, csv_text):
    f = StringIO(unidecode.unidecode(csv_text.lower()))
    reader = csv.DictReader(f, delimiter=",", skipinitialspace=True)
    script_components = [line for line in reader]

    print(csv_text)
    print(" ")
    print(script_components)

    tm1 = time.perf_counter()
    audio_base64 = []
    animation_script = generate_animation_file(script_components)
    with concurrent.futures.ThreadPoolExecutor() as executor:
        client_calls = build_script_client_calls(config, script_components, tts_client)
        futures = []

        for client_call in client_calls:
            futures.append(executor.submit(client_call))

        concurrent.futures.wait(futures)
        audio_base64 = [future.result()[1] for future in futures]

    tm2 = time.perf_counter()
    print(f"Total time elapsed for TTS: {tm2-tm1:0.2f} seconds")

    script_metadata = {
        # 2nd line should generally be the guest
        "guest_gender": script_components[1]["gender"]
    }

    return (animation_script, audio_base64, script_metadata)

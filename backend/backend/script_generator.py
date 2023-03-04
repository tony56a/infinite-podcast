import csv
import constants
import concurrent.futures
import time
import logging
import unidecode

from functools import partial
from io import StringIO

logger = logging.getLogger()


def get_script_component_text(component):
    return (
        component.get("text")
        or component.get("dialogue")
        or component.get("transcript")
    )


def build_script_client_calls(
    config, script_components, tts_client, script_type="normal", save_file=False
):
    voices = {
        "host": f"en_US/{config['tts']['host_voice']}",
        "male": f"en_US/{config['tts']['male_voice']}",
        "female": f"en_US/{config['tts']['female_voice']}",
    }

    client_calls = []
    for script_component in script_components:
        text = get_script_component_text(script_component)
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
                or script_type != "normal"
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


def generate_animation_file(script_components):
    animation_file = []

    for script_component in script_components[:-1]:
        text = get_script_component_text(script_component)
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
                "text": text,
            }
        )

    text = get_script_component_text(script_components[-1])
    animation_file.append(
        {"camera": 0, "characterPose": [0, 0], "length": 1, "text": text}
    )
    return animation_file


def generate_files(tts_client, config, csv_text, script_type):
    f = StringIO(unidecode.unidecode(csv_text.lower()))
    reader = csv.DictReader(f, delimiter=",", skipinitialspace=True)
    script_components = [line for line in reader]

    logger.info(
        f"Generating script for the following: {script_type} \n{csv_text} \n{script_components}"
    )

    tm1 = time.perf_counter()
    audio_base64 = []
    animation_script = generate_animation_file(script_components)
    with concurrent.futures.ThreadPoolExecutor() as executor:
        client_calls = build_script_client_calls(
            config, script_components, tts_client, script_type=script_type
        )
        futures = []

        for client_call in client_calls:
            futures.append(executor.submit(client_call))

        concurrent.futures.wait(futures)
        audio_base64 = [future.result()[1] for future in futures]

    tm2 = time.perf_counter()
    logger.info(f"Total time elapsed for TTS: {tm2-tm1:0.2f} seconds")

    script_metadata = {
        # 2nd line should generally be the guest
        "guest_gender": script_components[1]["gender"]
    }

    return (animation_script, audio_base64, script_metadata)

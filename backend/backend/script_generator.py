import csv
import constants
import concurrent.futures
import time
import logging
import unidecode
import random

from functools import partial
from io import StringIO

logger = logging.getLogger()


def get_script_component_text(component):
    retrieved_str = component.get("text")
    return str(retrieved_str).strip() if retrieved_str else None


def get_gender(guest_gender_str, script_type):
    guest_gender = "male"
    if guest_gender_str:
        guest_gender_str = guest_gender_str.lower()
        if (
            guest_gender_str == "m"
            or guest_gender_str == "male"
            or (
                script_type != "normal"
                and (guest_gender_str != "female" and guest_gender_str != "f")
            )
        ):
            guest_gender = "male"
        else:
            guest_gender = "female"
    return guest_gender


def _build_voice_map(config):
    male_voice = random.choice(config["tts"]["male_voice"])
    female_voice = random.choice(config["tts"]["female_voice"])

    voices = {
        "host": f"en_US/{config['tts']['host_voice'][0]}",
        "male": f"en_US/{male_voice[0]}",
        "female": f"en_US/{female_voice[0]}",
        "robot": f"en_US/{config['tts']['robot_voice'][0]}",
    }

    speeds = {
        "host": config["tts"]["host_voice"][1],
        "male": male_voice[1],
        "female": female_voice[1],
        "robot": config["tts"]["robot_voice"][1],
    }
    return (voices, speeds)


def build_script_client_calls(
    config,
    script_components,
    tts_client,
    script_type="normal",
    save_file=False,
    guest_gender=None,
    scene_type=None,
):
    client_calls = []
    voices, speeds = _build_voice_map(config)
    logger.info(f"Using voices {voices}")
    for script_component in script_components:
        text = get_script_component_text(script_component)

        text = text.strip().strip('"').strip("'").strip()

        is_host = (
            constants.DEFAULT_NAME.lower() in script_component["name"].lower()
            or "poe" in script_component["name"].lower()
        )
        if is_host:
            voice = voices["host"]
            speed = speeds["host"]
        else:
            voice = (
                voices[guest_gender] if script_type != "robot" else voices[script_type]
            )
            speed = (
                speeds[guest_gender] if script_type != "robot" else speeds[script_type]
            )

        if scene_type in config["tts"]["scene_type_modifier"]:
            speed *= config["tts"]["scene_type_modifier"][scene_type]

        client_calls.append(
            partial(
                tts_client.generate_tts_audio,
                text=text,
                voice=voice,
                save_file=save_file,
                speed=speed,
            )
        )

    return client_calls


def generate_animation_file(script_components):
    animation_file = []

    for script_component in script_components[:-1]:
        text = get_script_component_text(script_component)
        text = text.strip().strip('"').strip("'").strip()

        is_host = (
            constants.DEFAULT_NAME.lower() in script_component["name"].lower()
            or "poe" in script_component["name"].lower()
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
    text = text.strip().strip('"').strip("'").strip()
    animation_file.append(
        {"camera": 0, "characterPose": [0, 0], "length": 1, "text": text}
    )
    return animation_file


def generate_files(tts_client, config, csv_text, guest_type, scene_type):
    f = StringIO(unidecode.unidecode(csv_text))
    reader = csv.DictReader(
        f, delimiter="|", skipinitialspace=True, quoting=csv.QUOTE_NONE
    )
    script_components = [line for line in reader]

    logger.info(
        f"Generating script for the following: {guest_type} \n{csv_text} \n{script_components}"
    )
    script_components = [
        line
        for line in script_components
        if line.get("name") != None
        and line.get("gender") != None
        and line.get("text") != None
    ]
    # Apparently AI generation can result in voice switching
    guest_gender = script_components[1]["gender"].strip().strip('"').strip("'").strip()
    guest_gender = get_gender(guest_gender, guest_type)

    tm1 = time.perf_counter()
    audio_base64 = []
    animation_script = generate_animation_file(script_components)
    with concurrent.futures.ThreadPoolExecutor() as executor:
        client_calls = build_script_client_calls(
            config,
            script_components,
            tts_client,
            script_type=guest_type,
            guest_gender=guest_gender,
            scene_type=scene_type,
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
        "guest_gender": guest_gender
    }

    return (animation_script, audio_base64, script_metadata)

import csv
import constants

from io import StringIO
from ssml_builder.core import Speech


def build_script_ssml(config, script_components):
    voices = {
        "host": f"en_US/cmu-arctic_low#jmk",
        "male": f"en_US/cmu-arctic_low#fem",
        "female": f"en_US/cmu-arctic_low#slt",
    }
    speech = Speech()
    # add mimic3 voices to generator
    speech.VALID_VOICE_NAMES = tuple(voices.values())

    script_speech = []
    for script_component in script_components:
        text = script_component["text"] or script_component["dialogue"]
        is_host = "Poe Raegan".lower() in script_component["name"]
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


def generate_files(tts_client, config, csv_text):
    f = StringIO(csv_text.lower())
    reader = csv.DictReader(f, delimiter=",")
    script_components = [line for line in reader]
    ssml_script = build_script_ssml(config, script_components)
    audio_filepath = tts_client.generate_tts_audio(ssml_script, ssml=True)
    return ("", audio_filepath)

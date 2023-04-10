import constants

prompt_customizations = {
    "normal": ("human character", ""),
    "robot": (
        "robot",
        " and completely unrelated to robots, but referencing robots somehow",
    ),
    "skeleton": (
        "skeleton",
        " and completely unrelated to skeletons, but referencing skeletons somehow",
    ),
}


def generate_requested_script(
    prompt_customization, script_prompt, scene_type="podcast"
):
    prompt_templates = {
        "podcast": constants.ALT_API_PROMPT_TEMPLATE,
        "rapbattle": constants.API_RAP_BATTLE_PROMPT_TEMPLATE,
        "businesstalk": constants.API_BUSINESS_TALK_PROMPT_TEMPLATE,
    }

    return prompt_templates[scene_type].format(
        host_name=constants.DEFAULT_NAME,
        script_prompt=script_prompt,
        character_type=prompt_customization[0],
        character_addenda=prompt_customization[1],
    )

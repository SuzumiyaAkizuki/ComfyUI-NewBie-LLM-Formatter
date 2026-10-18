"""Parse final JSON envelopes before mode-specific prompt processing."""
from prompt_agent import utils
from prompt_agent.output_contract import parse_envelope


def parse_output(mode, content, config):
    if mode in ("Anima", "MOSS"):
        return parse_anima_output(content)
    return parse_newbie_output(content, config)


def parse_anima_output(content):
    return parse_envelope(content)


def parse_newbie_output(content, config):
    xml_content, text_content = parse_envelope(content)
    if "<img" not in xml_content.lower():
        raise ValueError("xml_out 中未检测到 <img> XML")
    gemma_prompt = config.get("gemma_prompt", "You are an assistant designed to generate high-quality anime images with the highest degree of image-text alignment based on xml format textual prompts. <Prompt Start>\n")
    return utils.clean_prompt(xml_content, gemma_prompt), text_content

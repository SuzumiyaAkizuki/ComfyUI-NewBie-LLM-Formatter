import os
import json
import re
from lxml import etree


class BColors:
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'


DEFAULT_STYLES = {
    "空样式，请在下方文本框中自行书写": {
        "artist": "",
        "style": ""
    }
}

CONFIG_FILENAME = "LPF_config.json"
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), CONFIG_FILENAME)


def load_styles_from_config():
    styles = DEFAULT_STYLES.copy()
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                user_styles = data.get("styles", {})
                if isinstance(user_styles, dict) and user_styles:
                    styles.update(user_styles)
        except Exception as e:
            print(f"{BColors.FAIL}[XML_Style_Injector]: 加载配置文件出错: {e}{BColors.ENDC}")
    return styles


# ---------------------------------------------------------------------------
# Tag parsing and formatting utilities
# ---------------------------------------------------------------------------

def _parse_nested_weight(tag_str):
    """
    Parse nested bracket weights like ((tag)), [tag], ([(tag)]).
    Returns (inner_content, computed_weight).
    Small parentheses () multiply by 1.2, square brackets [] multiply by 0.9.
    """
    weight = 1.0
    s = tag_str.strip()

    while len(s) >= 2:
        if s[0] == '(' and s[-1] == ')':
            weight *= 1.2
            s = s[1:-1].strip()
        elif s[0] == '[' and s[-1] == ']':
            weight *= 0.9
            s = s[1:-1].strip()
        else:
            break

    return s, round(weight, 2)


def parse_tag(tag_str):
    """
    Parse a single tag string into (content, weight).
    Supports three weight formats:
      1. (tag:1.2)       - parenthesized with explicit weight
      2. 1.2::tag::      - double-colon prefix format
      3. ((tag))         - nested brackets (1.2 per (), 0.9 per [])
    Returns (content: str, weight: float or None).
    """
    s = tag_str.strip()
    if not s:
        return '', None

    # Format 2: weight::content::
    m = re.match(r'^([\d.]+)::(.+)::$', s)
    if m:
        try:
            w = float(m.group(1))
            content = m.group(2).strip()
            return content, round(w, 2)
        except ValueError:
            pass

    # Format 1: (content:weight) - must have explicit :weight inside parens
    m = re.match(r'^\((.+):([\d.]+)\)$', s)
    if m:
        content = m.group(1).strip()
        try:
            w = float(m.group(2))
            return content, round(w, 2)
        except ValueError:
            pass

    # Format 3: nested brackets ((tag)), [tag], etc.
    if (s[0] in '([' and s[-1] in ')]'):
        # Check if balanced
        depth = 0
        balanced = True
        for ch in s:
            if ch in '([':
                depth += 1
            elif ch in ')]':
                depth -= 1
            if depth < 0:
                balanced = False
                break
        if balanced and depth == 0:
            inner, w = _parse_nested_weight(s)
            if w != 1.0:
                return inner, w

    # No weight
    return s, None


def _escape_parens(content):
    """Escape parentheses in tag content with backslashes."""
    s = content.replace('\\(', '\x00').replace('\\)', '\x01')  # preserve existing escapes
    s = s.replace('(', '\\(').replace(')', '\\)')
    s = s.replace('\x00', '\\(').replace('\x01', '\\)')
    return s


def format_tag_newbie(content, weight):
    """Format a tag for NewBie mode: keep underscores, escape parens in content."""
    escaped = _escape_parens(content)
    if weight is not None and weight != 1.0:
        return f"({escaped}:{weight})"
    return escaped


def format_tag_anima(content, weight):
    """Format a tag for Anima mode: underscores to spaces, escape parens, add @."""
    escaped = _escape_parens(content)
    escaped = escaped.replace('_', ' ')
    if not escaped.startswith('@'):
        escaped = f'@{escaped}'
    if weight is not None and weight != 1.0:
        return f"({escaped}:{weight})"
    return escaped


def parse_artist_string(artist_str):
    """
    Parse a comma-separated artist string into a list of (content, weight) tuples.
    """
    if not artist_str or not artist_str.strip():
        return []

    raw_tags = [t.strip() for t in artist_str.split(',') if t.strip()]
    result = []
    for tag in raw_tags:
        # Remove artist: prefix if present
        tag = re.sub(r'(?i)^artist:\s*', '', tag)
        # Remove orphan :: (single unmatched ones)
        # Valid format is weight::content::, so :: should appear in pairs
        # Count :: occurrences
        double_colon_count = tag.count('::')
        if double_colon_count == 1:
            # Single orphan :: - remove it
            tag = tag.replace('::', '')
        elif double_colon_count > 2:
            # Too many :: - try to extract valid pattern or clean up
            tag = tag.replace('::', '')

        content, weight = parse_tag(tag)
        if content:
            result.append((content, weight))
    return result


def format_artist_string(artist_str, mode):
    """
    Parse and reformat an artist string according to the specified mode.
    Returns formatted string with tags joined by ', '.
    """
    tags = parse_artist_string(artist_str)
    if not tags:
        return ""

    if mode == "NewBie":
        formatted = [format_tag_newbie(c, w) for c, w in tags]
        return ', '.join(formatted)
    else:  # Anima
        formatted = [format_tag_anima(c, w) for c, w in tags]
        return 'use the fixed style of ' + ' and '.join(formatted)


def deduplicate_tags(base_tags, override_tags):
    """
    Merge two tag lists, override_tags takes precedence over base_tags.
    Comparison is done on the raw content (before formatting).
    Returns merged list as (content, weight) tuples.
    """
    # Build dict from base, then override
    tag_dict = {}
    for content, weight in base_tags:
        tag_dict[content] = weight
    for content, weight in override_tags:
        tag_dict[content] = weight
    # Return in order: base order first, then new override tags
    base_contents = {c for c, _ in base_tags}
    override_only = [(c, w) for c, w in override_tags if c not in base_contents]

    result = []
    for content, weight in base_tags:
        if content in tag_dict:
            result.append((content, tag_dict[content]))
            del tag_dict[content]
    # Add remaining override tags
    for content, weight in override_only:
        result.append((content, weight))

    return result


def _is_anima_artist_tag(tag_str):
    """Check if a string looks like an Anima artist tag (starts with @)."""
    return tag_str.strip().startswith('@')


def _strip_anima_artists_from_text(text):
    """
    Remove all @artist tags from Anima prompt text.
    Returns (cleaned_text, first_artist_position).
    first_artist_position is the index where the first @artist was found, or -1.
    """
    lines = text.split('\n')
    first_pos = -1

    for i, line in enumerate(lines):
        # Find all @artist tags in this line
        # Pattern: @ followed by non-comma chars, possibly with weight like (@tag:1.2)
        matches = list(re.finditer(r'@[^,\n]+', line))
        if matches:
            if first_pos == -1:
                first_pos = i
            # Remove artist tags from line
            for m in reversed(matches):
                line = line[:m.start()] + line[m.end():]
            # Clean up leftover commas and spaces
            line = re.sub(r'\s*,\s*,\s*', ', ', line)
            line = line.strip(' ,')
            lines[i] = line

    return '\n'.join(lines), first_pos


def inject_anima_style(prompt_text, artist_tags, style_str):
    """
    Inject artist and style into an Anima-mode plain text prompt.
    Rules:
      - Remove all existing @artist tags from prompt
      - Append artist block at the end (before style)
      - Append style at the end
      - Final order: [original prompt][artist injection][style injection]
      - If a field is empty, leave the original untouched
    artist_tags: list of (content, weight) tuples, or None/empty
    style_str: plain text style string
    """
    has_artists = artist_tags and len(artist_tags) > 0
    has_style = style_str and style_str.strip()

    if not has_artists and not has_style:
        return prompt_text

    if has_artists:
        formatted = [format_tag_anima(c, w) for c, w in artist_tags]
        formatted_artists = 'use the fixed style of ' + ' and '.join(formatted)
    else:
        formatted_artists = ""

    # Strip existing artists
    cleaned_text, _ = _strip_anima_artists_from_text(prompt_text)

    lines = cleaned_text.split('\n')

    # Append artist at end (before style)
    if formatted_artists:
        lines.append(formatted_artists)

    # Append style at end
    if has_style:
        lines.append(style_str.strip())

    return '\n'.join(lines)


class LLM_Xml_Style_Injector:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        current_styles = load_styles_from_config()
        style_keys = list(current_styles.keys())

        return {
            "required": {
                "xml_input": ("STRING", {"forceInput": True}),
                "mode": (["NewBie", "Anima"],),
                "preset": (style_keys,),
            },
            "optional": {
                "artist_add": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "在此输入要添加的 Artist，将拼接到预设前面"
                }),
                "style_add": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "在此输入要添加的 Style，将拼接到预设前面"
                }),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("xml_output",)
    FUNCTION = "inject_style"
    CATEGORY = "NewBie LLM Formatter"

    def inject_style(self, xml_input, mode, preset, artist_add, style_add):
        current_styles = load_styles_from_config()
        selected_data = current_styles.get(preset, {"artist": "", "style": ""})

        preset_artist = selected_data.get("artist", "").strip()
        preset_style = selected_data.get("style", "").strip()

        # Combine artist tags with deduplication (artist_add overrides preset)
        if artist_add.strip() and preset_artist:
            add_tags = parse_artist_string(artist_add)
            preset_tags = parse_artist_string(preset_artist)
            merged_tags = deduplicate_tags(preset_tags, add_tags)
            target_artist_tags = merged_tags
        elif artist_add.strip():
            target_artist_tags = parse_artist_string(artist_add)
        else:
            target_artist_tags = parse_artist_string(preset_artist)

        # Combine style tags (simple concatenation, no dedup needed)
        def combine_tags(input_val, preset_val):
            input_val = input_val.strip()
            if input_val and preset_val:
                return f"{input_val}, {preset_val}"
            return input_val if input_val else preset_val

        target_style = combine_tags(style_add, preset_style)

        if mode == "Anima":
            result = inject_anima_style(xml_input, target_artist_tags or [], target_style)
            return (result,)

        # NewBie mode: XML injection
        # Format artist tags for NewBie
        if target_artist_tags:
            target_artist = ', '.join(format_tag_newbie(c, w) for c, w in target_artist_tags)
        else:
            target_artist = ""

        match = re.search(r'(<img>.*?</img>)', xml_input, re.DOTALL | re.IGNORECASE)

        if not match:
            print(f"{BColors.WARNING}[XML_Style_Injector]: 未发现 <img> 标签，跳过注入。{BColors.ENDC}")
            return (xml_input,)

        header_text = xml_input[:match.start()].strip()
        xml_content = match.group(1)

        try:
            parser = etree.XMLParser(recover=True, encoding='utf-8')
            root = etree.fromstring(xml_content.encode('utf-8'), parser=parser)

            def upsert(parent, tag_name, text_value):
                if text_value and text_value.strip():
                    elements = parent.xpath(f"//{tag_name}")
                    if elements:
                        for el in elements:
                            el.text = text_value
                    else:
                        print(f"{BColors.WARNING}[XML_Style_Injector]: 未找到<{tag_name}>标签，正在尝试注入<general_tags>{BColors.ENDC}")
                        gen_containers = parent.xpath("//general_tags")
                        if gen_containers:
                            new_node = etree.SubElement(gen_containers[0], tag_name)
                            new_node.text = text_value
                        else:
                            print(f"{BColors.WARNING}[XML_Style_Injector]: 未找到<general_tags>标签{BColors.ENDC}")
                            new_node = etree.SubElement(parent, tag_name)
                            new_node.text = text_value
                else:
                    print(f"{BColors.WARNING}[XML_Style_Injector]: 用户未输入<{tag_name}>，不改变标签{BColors.ENDC}")

            upsert(root, "artist", target_artist)
            upsert(root, "style", target_style)

            modified_xml = etree.tostring(root, encoding='unicode', method='xml', pretty_print=True)
            final_output = f"{header_text}\n{modified_xml}" if header_text else modified_xml
            return (final_output,)

        except Exception as e:
            print(f"{BColors.FAIL}[XML_Style_Injector]: XML 解析失败: {e}{BColors.ENDC}")
            return (xml_input,)
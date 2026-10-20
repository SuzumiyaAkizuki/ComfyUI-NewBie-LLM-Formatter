"""Local model-input specifications, separate from downstream presentation rules.

prompt_formats.json is a checked-in snapshot of the upstream MCP shared source.
Runtime never imports the upstream checkout or requires YAML/network access.
"""

import json
from functools import lru_cache
from pathlib import Path


MOSS_INTEGRATION_RULES = """
## MOSS 输出格式要求

### 提示词规则

遵循用户对 caption 或 Layout 的明确要求。否则，对于普通场景、照片和插画，使用 caption。当特定文本放置、海报、多个面板或受控的物体关系会受益于边界框时，使用 Layout。详细的图像并不自动需要 Layout。
关于 caption 或 layout 的详细说明，请调用 get_moss_image_format 工具查看。
保留用户的主体、数量、关系、媒介、风格、排除项和预期可见文字。自行解决普通的创意空白；
本模型的 captain 模式支持 Danbooru 标签列表（tag 串）式提示词，也支持自然语言式提示词。你也可以将两者混合使用。
为了在 tag 串中实现最好的性能, 推荐使用 Quality -> Score -> Meta -> Year -> Character -> Series -> Artist -> General 的顺序构造.示例：
> best quality, highres, hatsune miku, vocaloid, @foo bar, 1girl, blue hair
你应当在 caption 或 Layout 的自然语言部分中尽可能使用已确认的 Danbooru 标签词汇。对于标签无法描述的内容，也可以用自然语言进行描述。

### 工具调用规则

有工具可用时先调用 get_moss_image_format 获取规范；
Layout 使用原始像素 abs/xyxy 草稿坐标，禁止自行换算。
按 get_moss_image_format 返回的 MOSS 规范组织 caption 或 Layout 草稿。
所有最终提示词（包括普通 caption）都必须在现有工具循环中调用 compile_moss_prompt 编译。
编译失败时修正草稿并重试；禁止跳过编译或交付错误信息。

### 输出格式规则

最终以 JSON 的 xml_out 字符串返回提示词，以 text_out 字符串返回中文解释。
成功后 xml_out 必须逐字等于最近一次 compile_moss_prompt 的返回值，禁止再改写。
最终 xml_out 必须是可直接用于 MOSS 的提示词字符串，不是等待编排器编译的草稿包装。
text_out 说明实际采用的标签与设计，并完整翻译英文自然语言；需要画布尺寸时也在这里说明。

"""

@lru_cache(maxsize=1)
def _load_formats():
    path = Path(__file__).with_name("prompt_formats.json")
    formats = json.loads(path.read_text(encoding="utf-8"))
    for mode in ("NewBie", "Anima", "MOSS"):
        if not isinstance(formats.get(mode), str) or not formats[mode].strip():
            raise ValueError(f"本地格式规范缺少非空文本: {mode}")
    return formats


def get_format_spec(mode):
    """Return only the model-input specification; presentation is added separately."""
    return _load_formats()[mode]


def get_system_additions(mode, config):
    """Legacy system_prompt* fields are intentionally never merged into the spec."""
    key = {"NewBie": "system_prompt_extra", "Anima": "system_prompt_extra_anima",
           "MOSS": "system_prompt_extra_moss"}[mode]
    sections = [MOSS_INTEGRATION_RULES] if mode == "MOSS" else []
    extra = config.get(key, "")
    if isinstance(extra, str) and extra.strip():
        sections.append("## 用户补充要求\n" + extra.strip())
    return "\n\n".join(sections)

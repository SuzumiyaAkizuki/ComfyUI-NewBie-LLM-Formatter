# ComfyUI-NewBie-LLM-Formatter

[![ComfyUI](https://img.shields.io/badge/ComfyUI-Compatible-green.svg)](https://comfy.org/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![NewBie](https://img.shields.io/badge/NewBie-Compatible-yellow.svg)](https://huggingface.co/NewBie-AI/NewBie-image-Exp0.1)

![](https://akizukipic.oss-cn-beijing.aliyuncs.com/img/202602100940021.png)

利用大语言模型 API 将自然语言或图片自动转化为适用于 NewBie 模型的结构化 XML 提示词，或适用于 Anima 等其他模型的纯文本提示词。通过提供高度健壮的提示词生成与画面风格管理节点，显著提升了图像生成流程的效率与效果。

本插件的核心特性有：

- **双模式支持**：NewBie 模式生成结构化 XML 提示词；Anima 模式生成纯文本提示词（质量词 + 标签 + 自然语言描述），两种模式可在节点内无缝切换。
- **智能提示词转化**：支持将简单的自然语言、Danbooru 标签串，完美转化为目标模型所需的提示词格式。
- **多模态视觉反推**：支持传入图片，利用多模态大模型直接反推生成高精度提示词。
- **高鲁棒性与自动修复**：内置 XML 语法解析与自动修复机制，外加 API 网络异常/格式异常自动重试逻辑（最高 3 次），确保工作流不中断。
- **画风预设与管理**：内置数十种高质量艺术家/画风预设，支持一键注入，并提供在 UI 中直接保存新画风的节点。
- **深度思考与破限支持**：适配主流 API 的"深度思考"模式（Deepseek、OpenRouter、Gemini、Anthropic、Kimi、MIMO、Vercel 等），内置 NSFW 提示词破限框架。

- 项目 GitHub 地址：https://github.com/SuzumiyaAkizuki/ComfyUI-NewBie-LLM-Formatter
- 项目 ComfyUI Registry 地址：https://registry.comfy.org/zh/nodes/NewBie-LLM-Formatter

---

## 目录

- [安装和使用方法](#安装和使用方法)
- [配置文件说明](#配置文件说明)
- [节点说明](#节点说明)
- [依赖](#依赖)
- [参考工作流](#参考工作流)
- [更新说明](#更新说明)

---

## 安装和使用方法

### 方法一：命令行安装（推荐）

```bash
comfy node install NewBie-LLM-Formatter
```

### 方法二：手动安装

1. 点击 GitHub 页面中绿色按钮 `<> Code`，点击 **Download ZIP**，下载压缩包。

   ![下载按钮](https://akizukipic.oss-cn-beijing.aliyuncs.com/img/202512211546384.png)

   ![压缩包](https://akizukipic.oss-cn-beijing.aliyuncs.com/img/202512211548632.png)

2. 将解压后的文件夹放置在 `...\ComfyUI\custom_nodes\` 目录下。

   ![image-20251226145335813](https://akizukipic.oss-cn-beijing.aliyuncs.com/img/202512261453308.png)

3. 进入文件夹，找到 `LPF_config.json.example` 文件，右键重命名，删掉 `.example` 后缀，使其变为 `LPF_config.json`。

   ![重命名前](https://akizukipic.oss-cn-beijing.aliyuncs.com/img/202512261454909.png)

   ![image-20251226145521692](https://akizukipic.oss-cn-beijing.aliyuncs.com/img/202512261455772.png)

4. 使用记事本或文本编辑器打开 `LPF_config.json`，按照下方[配置文件说明](#配置文件说明)填写对应字段。

   ![填写前后对比](https://akizukipic.oss-cn-beijing.aliyuncs.com/img/202512261457930.png)

5. 重启 ComfyUI，即可使用。

---

## 配置文件说明

插件的所有配置均集中在 `LPF_config.json` 中。以下是各字段的完整说明：

| 字段 | 类型 | 说明 |
|------|------|------|
| `api_key` | `string` | LLM 的 API Key。**强烈建议在此处填写，而非在节点 UI 中输入**，否则 API Key 会随工作流原图泄露。 |
| `api_url` | `string` | API 服务的主机地址，例如 `https://openrouter.ai/api/v1`。 |
| `model_list` | `array` | 可用模型名称列表，将显示在节点的下拉框中。 |
| `system_prompt` | `string` | **NewBie 模式**发送给 LLM 的系统提示词，内置了基本的格式化指令和破限命令。可自行修改以调整 LLM 的行为。 |
| `gemini_jailbreaker` | `string` | 针对非 Gemini 官方平台的 Gemini 模型的增强提示词，会拼接在 `system_prompt` 之前。仅在使用非官方 Gemini API 中转时生效。 |
| `fewshot_user` | `string` | **NewBie模式**Few-shot 注入功能：此字段为注入的一轮对话中「用户」的内容。与 `fewshot_assistant` 同时填写时生效。 |
| `fewshot_assistant` | `string` | **NewBie模式**Few-shot 注入功能：此字段为注入的一轮对话中「AI」的回复内容。可用于增强模型在特定方面的输出能力。 |
| `gemma_prompt` | `string` | 拼接在 **NewBie 模式** XML 输出前的固定引导词，用于指导 NewBie 模型（Gemma3 4B）理解提示词格式。通常无需修改。Anima 模式下不使用此字段。 |
| `system_prompt_anima` | `string` | **Anima 模式**发送给 LLM 的系统提示词。需要指导模型输出格式为：第一行质量词、第二行有含义的标签、第三行英文自然语言描述、第四行中文描述（作为 `text_out` 输出）。 |
| `fewshot_user_anima` | `string` | **Anima模式**Few-shot 注入功能。与 `fewshot_assistant_anima` 同时填写时生效。 |
| `fewshot_assistant_anima` | `string` | **Anima模式**Few-shot 注入功能。 |
| `artists_anima` | `string` | **Anima模式**参考画师列表，指导LLM选择合适的画师。可以在[这个视频](https://www.bilibili.com/video/BV1Q1w1zKEwk)或者[这个链接](https://drive.google.com/file/d/1CtcODfWbDl8KThORS0GHZfcWKCCMUUmD/view)中下载对应的内容。为保护作者的知识产权，这里不提供对应的文本。 |
| `styles` | `object` | 预设风格提示词集合，供 XML Style Injector 节点使用。可通过 Style Preset Saver 节点或直接编辑此文件来添加风格。 |

### Anima 模式提示词格式

`system_prompt_anima`要求 LLM 输出以换行分隔的四段内容

```
Line 1: quality and aesthetic tags (e.g. masterpiece, score_9, ...)
Line 2: subject and scene tags (e.g. 1girl, white_hair, ...)
Line 3: English natural language description
Line 4: 中文自然语言描述（将作为 text_out 输出）
```

### Few-shot 注入的请求体结构

> 开发者笔记：few-shot技术是一种提示词工程，旨在通过在提示中提供少量输入-输出示例，让大语言模型快速理解任务模式并生成符合预期的回答。出于某些原因，我无法提供few-shot的示例内容。但是，你可以利用某些方面能力更强的LLM（比如grok）生成一轮示例对话，并填入few-shot注入词中，之后改用其它通用能力更强的LLM（比如gemini）。

当 `fewshot_user` 和 `fewshot_assistant` 均不为空时，请求体结构如下：

```python
messages = [
    {"role": "system",    "content": system_prompt},
    {"role": "user",      "content": fewshot_user},       # 注入的示例用户输入
    {"role": "assistant", "content": fewshot_assistant},  # 注入的示例 AI 回复
    {"role": "user",      "content": 用户在节点中输入的内容}
]
```

### API 配置优先级

配置文件中的值 **优先于** 节点 UI 中填写的值。具体逻辑如下：

1. 程序首先读取 `LPF_config.json` 中的 `api_key` 和 `api_url`；
2. 若配置文件中存在有效值，则使用配置文件的值，**节点 UI 中的输入不会生效**；
3. 若配置文件中无有效值，则回退使用节点 UI 中的输入。

> ⚠️ **安全提示**：在节点 UI 中填写的 API Key 会被保存在工作流文件中，**分享工作流原图即导致 API Key 泄露**。强烈建议始终使用配置文件进行配置。

---

## 节点说明

ComfyUI-NewBie-LLM-Formatter 提供三个节点：

### 1. LLM Xml Prompt Formatter

**功能：** 调用 LLM API，将用户输入的自然语言或标签集格式化为提示词，根据所选模式输出 XML 格式（NewBie）或纯文本格式（Anima）。

**输入参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `image` | IMAGE（可选） | 输入图片，传输给多模态 LLM 进行提示词反推。注意：这是让 LLM 反推提示词，而非图生图。 |
| `api_key` | STRING | API Key。若配置文件中已有有效值，此处输入不生效。 |
| `api_url` | STRING | API 主机地址。若配置文件中已有有效值，此处输入不生效。 |
| `model_name` | STRING/下拉框 | 模型名称。若配置文件中的 `model_list` 有效，显示为下拉框；否则显示为文本输入框。 |
| `mode` | 下拉框 | **NewBie**（默认）或 **Anima**。决定使用哪套 system prompt 以及输出解析方式。 |
| `thinking` | BOOLEAN | 深度思考模式开关。`true` 时模型进行深度思考，思考过程输出到控制台。**推荐设置为 `false`。** |
| `user_text` | STRING | 待转换的自然语言描述或标签集。 |

**输出参数：**

| 参数 | 说明 |
|------|------|
| `xml_out` | NewBie 模式：清洗并修复后的 XML 格式提示词。Anima 模式：LLM 输出中所有英文内容（质量词 + 标签 + 英文描述）。 |
| `text_out` | NewBie 模式：LLM 输出的 XML 代码块以外的额外说明信息。Anima 模式：LLM 输出中所有中文内容（通常为中文描述）。 |

**两种模式的行为差异：**

| 行为 | NewBie 模式 | Anima 模式 |
|------|------------|-----------|
| 使用的 system prompt | `system_prompt` | `system_prompt_anima` |
| `gemma_prompt` 前缀 | 拼接到输出前 | 不使用 |
| 输出解析 | 提取 XML 代码块，校验并修复格式 | 按行分离中英文，英文→`xml_out`，中文→`text_out` |
| XML 自动修复 | 启用 | 不启用 |

**内置鲁棒性机制：**

- **自动重试**：遇到网络抖动或 API 报错时，最多自动重试 3 次。
- **XML 自动修复**（仅 NewBie 模式）：使用 `lxml` 库对 LLM 输出的 XML 进行格式校验；若检测到格式错误，会自动修复并在控制台打印差异对比。

**推荐模型（计价参考 [OpenRouter](https://openrouter.ai/)，均关闭思考模式）：**

| 模型名称 | 平均每次成本/美元 | NSFW 效果 | 输出质量 | 备注 |
|----------|-----------------|-----------|----------|------|
| `deepseek/deepseek-v3.2` | ~0.0008 | 均衡 | 均衡 | 综合性价比高 |
| `google/gemini-3-flash-preview` | ~0.0035 | 较好（G 向需技巧） | 最好 | NewBie 训练打标模型之一 |
| `x-ai/grok-4.1-fast` | ~0.0007 | 最好 | 较好 | NewBie 训练打标模型之一 |
| `xiaomi/mimo-v2-flash` | ~0.0004 | 较好 | 一般 | — |
| `cognitivecomputations/dolphin-mistral-24b-venice-edition:free` | 免费 | 官方宣称无审查 | 较差 | — |

> **思考模式说明：** 目前适配了 OpenRouter、DeepSeek、Google AI、Anthropic 官方、Kimi、小米 MIMO 和 Vercel AI Gateway 平台。其他平台请通过模型名称控制（如用 `deepseek-chat` 代替 `deepseek-reasoner`）。
>
> **开发者建议：**
>
> - 强烈建议关闭思考模式。关闭时每次约消耗 3000–4000 tokens；开启时可能消耗 5000–10000 tokens，且关闭思考有时反而能提升 NSFW 效果。
> - 不建议使用参数量不远高于 4B 的模型。NewBie 本身已内置 Gemma3 4B，Anima已内置qwen3 0.6B，使用同等量级的外部 LLM 意义不大。
>
> **免费额度提示：** 在 [DeepSeek 开放平台](https://platform.deepseek.com) 注册后可获赠 10 元免费额度，大约可使用 1000 次。

<details open>
<summary>NewBie 模式节点示例输入输出</summary>

**纯文本示例输入：**

```
A:(loli,(blonde hair:1.2),hair between eyes,short hair,ahoge,twintails,short tail,short_kimono,white socks,Frilled socks,converse,sash,red_sash,sidelocks,low twintails, fingerless gloves, haori,shorts under skirt,hairclip,leg belt)

B:(white hair,high ponytail,white serafuku,short sleeves,short skirt,shirt tucked in,knee pads,elbow pads,fingerless gloves,white legwear,kneehighs,high-top hiking sneakers,sidelocks,shorts under skirt,)

在一个科幻风格的指挥所中，画面左侧，A担任一场战役的指挥官。她戴着耳麦，正在指挥战役。指挥所里有全息显示的显示屏和地图。画面右侧，B穿着战术马甲、戴着头盔、拿着狙击步枪，正在执行作战任务。这两个场景的画面要有机地融合在一起，动漫风格、油画风格。
```

**`xml_out` 示例输出：**

```xml
You are an assistant designed to generate high-quality anime images with the highest degree of image-text alignment based on xml format textual prompts. <Prompt Start>

<img>
 <character_1>
 <n>A</n>
 <gender>1girl</gender>
 <appearance>loli, blonde_hair:1.2, hair_between_eyes, short_hair, ahoge, twintails, short_tail, sidelocks, low_twintails, hairclip</appearance>
 <clothing>short_kimono, white_socks, frilled_socks, converse, sash, red_sash, fingerless_gloves, haori, shorts_under_skirt, leg_belt</clothing>
 <expression>serious, focused</expression>
 <action>wearing_headset, commanding, pointing_at_hologram</action>
 <position>left_side</position>
 </character_1>

 <character_2>
 <n>B</n>
 <gender>1girl</gender>
 <appearance>white_hair, high_ponytail, sidelocks</appearance>
 <clothing>white_serafuku, short_sleeves, short_skirt, shirt_tucked_in, knee_pads, elbow_pads, fingerless_gloves, white_legwear, kneehighs, high-top_hiking_sneakers, shorts_under_skirt, tactical_vest, helmet</clothing>
 <expression>determined, focused</expression>
 <action>holding_sniper_rifle, aiming, in_combat_stance</action>
 <position>right_side</position>
 </character_2>

 <general_tags>
 <count>2girls</count>
 <style>oil painting, anime_style, realistic_shading</style>
 <background>sci-fi_command_center, holographic_displays, tactical_map, futuristic_technology</background>
 <atmosphere>tense, strategic</atmosphere>
 <quality>very_aesthetic, masterpiece, no_text</quality>
 <resolution>max_high_resolution</resolution>
 <artist>rella, maccha_(mochancc), tidsean, wlop, ciloranko, atdan, year_2024</artist>
 <objects>headset, sniper_rifle, tactical_gear, holograms</objects>
 </general_tags>

 <caption>In a futuristic sci-fi command center filled with holographic displays and tactical maps, two girls are depicted in different roles...</caption>
</img>
```

</details>

<details open>
<summary>Anima 模式节点示例输入输出</summary>

**示例输入：**

```
A：1girl,white_hair,blue_eyes, medium_hair, high_ponytail, small_breasts, sidelocks,serafuku,deep_blue_skirt, white_shirt, deep_blue_sailor_collar,  short_sleeves, short_skirt, shirt_tucked_in,elbow_pads, fingerless_gloves, shorts_under_skirt,toned, tactical_school_uniform,red_neckerchief,utility belt

上述人物的上半身特写(upper_body, close-up)，从正面视角注视着观众(straight-on, facing_viewer)。她骄傲地挺胸抬头(confident, proud,arched_back)、并在眼睛上方比出“V”字手势的姿势(v_over_eye)，另一只手叉腰(hand_on_own_hip)。她戴着耳麦和战术头盔(fast helmet, headset)，全身（胸部、大腿）戴着攀岩时用的全身安全带(full body harness,chest harness,leg loops,waist belt)。她的头发和衣服被风吹动(wind_lift)。背景是充满活力的抽象构图，由多彩的玻璃碎片、蓝色和紫色调以及图形元素组成，保持了酷炫且时尚的氛围。

要求人物是萌系画风，可爱一点。
```

**`xml_out` 示例输出（英文部分）：**

```
masterpiece, best quality, good quality, score_9, score_8, score_7, year_2025, highres, @kantoku, @tiv, @mika_pikazo, @anmi,
1girl, white_hair, blue_eyes, medium_hair, high_ponytail, small_breasts, sidelocks, serafuku, white_shirt, deep_blue_skirt, deep_blue_sailor_collar, short_sleeves, short_skirt, shirt_tucked_in, red_neckerchief, utility_belt, shorts_under_skirt, elbow_pads, fingerless_gloves, toned, tactical_school_uniform, fast_helmet, headset, full_body_harness, chest_harness, leg_loops, waist_belt, upper_body, close-up, straight-on, facing_viewer, confident, proud, arched_back, v_over_eye, hand_on_hip, wind_lift, abstract_background, glass_shards, blue_theme, purple_theme, graphic_background,
An adorable girl with white hair and striking blue eyes poses confidently in her tactical sailor uniform. She stands with an arched back and one hand on her hip, making a cute "V" sign over her eye while looking directly at the viewer with a proud expression. Her high ponytail and white shirt flutter in the wind. She is equipped with a FAST helmet, headset, and a complex full-body climbing harness over her outfit. The background is a stylish and cool abstract composition featuring vibrant blue and purple glass shards and modern graphic elements.
```

**`text_out` 示例输出（中文部分）：**

```
一位拥有白发和深邃蓝眸的可爱女孩穿着她的战术水手服自信地摆出姿势。她挺起胸膛，一只手叉腰，在眼睛上方比出可爱的“V”字手势，带着骄傲的神情直视观众。她的高马尾和白色衬衫在微风中飘动。她佩戴着战术头盔、耳麦，并在制服外穿着一套复杂的全身攀爬安全带。背景是一个时尚酷炫的抽象构图，充满了充满活力的蓝色和紫色玻璃碎片以及现代图形元素。
```

</details>

---

### 2. XML Style Injector

**功能：** 将画师和风格信息注入到提示词中，支持 NewBie（XML）和 Anima（纯文本）两种模式。

**输入参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `xml_input` | STRING | 待处理的提示词文本。NewBie 模式下应为含 `<img>` 标签的 XML；Anima 模式下应为换行分隔的纯文本。 |
| `mode` | 下拉框 | **NewBie** 或 **Anima**，需与 LLM Xml Prompt Formatter 节点的模式保持一致。 |
| `preset` | 下拉框 | 选择预设风格提示词集合，内容来自 `LPF_config.json` 的 `styles` 字段。 |
| `artist_add` | STRING（可选） | 额外的画师标签，将**拼接在预设画师列表之前**。 |
| `style_add` | STRING（可选） | 额外的风格标签，将**拼接在预设风格列表之前**。 |

**输出参数：**

| 参数 | 说明 |
|------|------|
| `xml_output` | 注入风格后的提示词。 |

**NewBie 模式行为：**

查找 XML 中的 `<artist>` 和 `<style>` 标签并替换为选定预设的内容。若 XML 中不存在对应标签，节点会尝试在 `<general_tags>` 容器下创建。若对应字段为空，则不修改原标签内容。

**Anima 模式行为：**

> 开发者笔记：适用于NewBie模型的画风串不一定适用于Anima模型。

Anima 模式下的画师和风格注入逻辑：

- **画师注入位置**：注入到第一行（质量词行）之后。若第二行已是独立的画师行（整行均为 `@xxx` 格式），则整行替换；否则先清除第一行中内嵌的 `@xxx` 标记，再在其后插入新画师行。
- **风格注入位置**：追加到整个提示词的最末尾。
- **空字段行为**：若 `artist_add` 和预设画师均为空，则不修改画师内容；若风格字段均为空，则不追加风格，保持原内容不变（与 NewBie 模式对齐）。

**Anima 模式画师格式：**

输入的画师字符串在注入前会经过以下清洗步骤：

1. 删除方括号、大括号、圆括号：`[ciloranko]` → `ciloranko`
2. 删除 `artist:` 前缀（大小写不敏感）：`artist:rella` → `rella`
3. 删除冒号权重（`:1.2`、`:0.93` 等），再删除所有剩余冒号
4. 删除独立的数字/小数（不紧邻字母或下划线的数字）：`wlop 1.1` → `wlop`；`year_2024` 中的 `2024` 紧邻下划线，保留
5. 将名称内部空格替换为下划线：`some artist` → `some_artist`
6. 为每个名称添加 `@` 前缀：`rella` → `@rella`

示例：`[ciloranko], maccha_(mochancc), (tidsean:1.2), wlop 1.1, year_2024`
→ `@ciloranko, @maccha_mochancc, @tidsean, @wlop, @year_2024`

配置文件内置约 40 个预设风格串，可在[此链接](https://docs.qq.com/sheet/DTUNCQW5TWFBMVGhY?tab=BB08J2)查看例图。

---

### 3. Style Preset Saver

**功能：** 从当前提示词中自动提取 `<artist>` 和 `<style>` 标签，并将其保存为新的风格预设到 `LPF_config.json` 中，方便后续在 XML Style Injector 中调用。

**输入参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `text_input` | STRING | 输入包含 `<artist>` 和/或 `<style>` 标签的提示词文本，节点将自动解析这两个字段的内容。 |
| `preset_name` | STRING | 新预设的名称。若名称为空或与已有预设重名，节点将放弃保存。 |
| `save_trigger` | BOOLEAN | 保存开关。仅当显示 `Save as Styles` 时才会执行保存操作；显示 `Do Not Save` 时仅提取不保存。 |

**输出参数：**

| 参数 | 说明 |
|------|------|
| `extracted_tags` | 从输入中提取到的风格标签预览，格式为 `<artist>...</artist>\n<style>...</style>`，无论是否保存均会输出。 |

> **注意：** Style Preset Saver 目前仅支持从 XML 格式（NewBie 模式）的提示词中提取标签。预设保存格式与模式无关，保存后的预设可在 NewBie 和 Anima 两种模式下的 XML Style Injector 中使用。

---

## 依赖

请参考项目中的 `requirements.txt`，主要依赖包括：

- `openai`：用于调用 LLM API（兼容 OpenAI 格式的接口）
- `lxml`：用于 XML 解析、校验与自动修复

---

## 参考工作流

示例工作流保存在项目的 `NewBie_LLM_Formatter_example.json` 中。

**加载方法：** 右键另存为 → 打开 ComfyUI → 按 <kbd>Ctrl</kbd>+<kbd>O</kbd> → 选择此文件。

此工作流是一个完整、成熟的工作流，包含了其他辅助节点，并附有详细注释。

---

## 更新说明

<details open>
<summary>展开/折叠更新历史</summary>

### 2026年04月08日 v1.2.5 [exp]

> 此版本是实验性版本，未经大量测试用例测试，可能存在BUG。

- 新增 **Anima 模式**，支持生成适用于 Anima 模型的纯文本提示词（质量词 + 标签 + 自然语言描述）。
  - LLM Xml Prompt Formatter 和 XML Style Injector 均新增 `mode` 单选控件（NewBie / Anima）。
  - Anima 模式使用独立的 `anima_system_prompt` 配置字段；不使用 `gemma_prompt` 前缀；跳过 XML 解析，直接按行分离中英文。
  - Anima 模式风格注入：画师以 `@画师名` 格式注入到质量词行之后，风格串追加到末尾；若对应字段为空则不修改原内容。
  - Anima 模式画师字符串清洗：自动去除括号、`artist:` 前缀、冒号权重及独立数字、将空格替换为下划线。
- 新增 **Anthropic、Kimi、Vercel AI Gateway** 三个平台的深度思考控制支持。
- 更新了很多预设风格串。

### 2026年03月17日 v1.2.3

- 增加了 LLM 输出异常时的自动重试逻辑（最多重试 3 次），遇到网络抖动或 API 报错时更加稳健。
- 在配置文件中预留了 few-shot 上下文注入接口（`fewshot_user` / `fewshot_assistant` 字段）。详见[配置文件说明](#配置文件说明)。

### 2026年02月25日 v1.2.2

- 新增了大量预设风格串。可在[此链接](https://docs.qq.com/sheet/DTUNCQW5TWFBMVGhY?tab=BB08J2)查看内置预设风格串的例图。

### 2026年02月22日 v1.2.1

- 修复了 system prompt 中的若干问题；新增部分预设风格串。

### 2026年02月10日 ComfyUI-DanbooruSearcher

- 发布了新项目 [ComfyUI-DanbooruSearcher](https://github.com/SuzumiyaAkizuki/ComfyUI-DanbooruSearcher)，用于模糊搜索 Danbooru 标签，可与本插件配合使用以提升输出标签质量。

### 2026年02月06日 v1.2.0

- 大幅重构代码，优化各项逻辑。

### 2026年02月01日 v1.1.9

- 大幅重构代码，优化各项逻辑。

### 2026年01月30日 v1.1.8

- 新增思考模式对小米 MIMO 平台的支持。
- 优化示例配置文件；更新预设风格。

### 2026年01月12日 v1.1.7

- 大幅提升**非 Gemini 官方平台**下 Gemini 模型的 NSFW 生成能力。若仍然失败（多见于 G 向），可尝试在敏感词中插入字符以破坏 token（如 `blood` → `blo···od`）。

  > 开发者注：不同 API 中转平台的破限效果存在差异，其中 [OpenRouter](https://openrouter.ai/) 效果最佳。Gemini 官方平台在加入强力破限词后反而可能导致无输出，故官方平台不做破限适配。
  
- 优化思考模式开关逻辑，支持 Gemini 官方平台；对不支持的平台不再报错，仅打印警告。
- 更新示例工作流。

### 2026年01月08日 v1.1.6

- Style Preset Saver 新增 `extracted_tags` 输出流，可在保存前预览将要保存的风格提示词组。
- 修复若干 bug，优化用户引导信息。

### 2026年01月07日 v1.1.5

- 新增 Style Preset Saver 节点，支持将自定义风格提示词组保存到配置文件。
- LLM Xml Prompt Formatter 新增思考模式开关按钮；思考内容将在控制台输出。
- LLM Xml Prompt Formatter 在控制台输出每次请求消耗的 token 数量。
- 更新更多预设风格提示词组；更新 README，增加 LLM 评测表格。

### 2026年01月03日 v1.1.0

- 更新更多预设风格提示词组。
- 新增 `requirements.txt`，支持自动安装依赖。

### 2025年12月26日 v1.0.7

- LLM Xml Prompt Formatter 新增可选图片输入流，支持多模态 LLM 进行图片提示词反推。
- 优化 system prompt，减少 token 消耗。

### 2025年12月24日 v1.0.5

- 修改提示词结构，LLM 输出严格遵循 XML 格式。
- LLM 输出后进行 XML 格式检查与自动修复（基于 `lxml`），降低格式错误率。
- 将原先的正则表达式匹配法改为 XML 解析方式进行数据清洗和标签注入，增强程序鲁棒性。
- 新增依赖 [lxml](https://github.com/lxml/lxml)。

### 2025年12月22日 v1.0.0

- 统一文件结构：所有节点配置集中到 `LPF_config.json`。
- 修复分享工作流原图时暴露 API Key 的问题。
- 新增 JSON 文件编辑小工具。
- 优化默认 system prompt，节约 token。
- 新增 LLM 输出清洗流程，增强程序鲁棒性。

</details>

---

## 其他

NewBie 模型官方用户群：**1019424838**
# ComfyUI-NewBie-LLM-Formatter

[![ComfyUI](https://img.shields.io/badge/ComfyUI-Compatible-green.svg)](https://comfy.org/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![NewBie](https://img.shields.io/badge/NewBie-Compatible-yellow.svg)](https://huggingface.co/NewBie-AI/NewBie-image-Exp0.1)

![](https://akizukipic.oss-cn-beijing.aliyuncs.com/img/202602100940021.png)

利用大语言模型 API 将自然语言或图片自动转化为适用于 NewBie 模型的结构化 XML 提示词。通过提供高度健壮的提示词生成与画面风格管理节点，显著提升了图像生成流程的效率与效果。

本插件的核心特性有：

-  **智能提示词转化**：支持将简单的自然语言、Danbooru 标签串，完美转化为 NewBie 模型所需的标准 XML 格式。
-  **多模态视觉反推**：支持传入图片，利用多模态大模型直接反推生成高精度 XML 提示词。
-  **高鲁棒性与自动修复**：内置 XML 语法解析与自动修复机制，外加 API 网络异常/格式异常自动重试逻辑（最高 3 次），确保工作流不中断。
-  **画风预设与管理**：内置数十种高质量艺术家/画风预设，支持一键注入，并提供在 UI 中直接保存新画风的节点。
-  **深度思考与破限支持**：适配主流 API 的“深度思考”模式（Deepseek, OpenRouter, Gemini, MIMO 等），内置 NSFW 提示词破限框架。

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
| `system_prompt` | `string` | 发送给 LLM 的系统提示词，内置了基本的格式化指令和破限命令。可自行修改以调整 LLM 的行为。 |
| `gemma_prompt` | `string` | 拼接在 XML 输出前的固定引导词，用于指导 NewBie 模型（Gemma）理解提示词格式。通常无需修改。 |
| `gemini_jailbreaker` | `string` | 针对非 Gemini 官方平台的 Gemini 模型的增强提示词，会拼接在 `system_prompt` 之前。仅在使用非官方 Gemini API 中转时生效。 |
| `fewshot_user` | `string` | Few-shot 注入功能：此字段为注入的一轮对话中「用户」的内容。与 `fewshot_assistant` 同时填写时生效。 |
| `fewshot_assistant` | `string` | Few-shot 注入功能：此字段为注入的一轮对话中「AI」的回复内容。可用于增强模型在特定方面的输出能力。 |
| `styles` | `object` | 预设风格提示词集合，供 XML Style Injector 节点使用。可通过 Style Preset Saver 节点或直接编辑此文件来添加风格。 |

### Few-shot 注入的请求体结构

> 开发者笔记：few-shot技术是一种提示词工程，旨在通过在提示中提供少量输入-输出示例，让大语言模型快速理解任务模式并生成符合预期的回答。出于某些原因，我无法提供few-shot的示例内容。但是，你可以利用某些方面能力更强的LLM（比如grok）生成一轮示例对话，并填入few-shot注入词中，之后改用其它通用能力更强的模型（比如gemini）。

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

**功能：** 调用 LLM API，将用户输入的自然语言或标签集格式化为 `xml` 格式提示词，供 NewBie 模型使用。

![image-20260113122948204](https://akizukipic.oss-cn-beijing.aliyuncs.com/img/202601131230416.png)

**输入参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `image` | IMAGE（可选） | 输入图片，传输给多模态 LLM 进行提示词反推。注意：这是让 LLM 反推提示词，而非图生图。 |
| `api_key` | STRING | API Key。若配置文件中已有有效值，此处输入不生效。 |
| `api_url` | STRING | API 主机地址。若配置文件中已有有效值，此处输入不生效。 |
| `model_name` | STRING/下拉框 | 模型名称。若配置文件中的 `model_list` 有效，显示为下拉框；否则显示为文本输入框。 |
| `thinking` | BOOLEAN | 深度思考模式开关。`true` 时模型进行深度思考，思考过程输出到控制台。**推荐设置为 `false`。** |
| `user_text` | STRING | 待转换的自然语言描述或标签集。 |

**输出参数：**

| 参数 | 说明 |
|------|------|
| `xml_out` | 清洗并修复后的 `xml` 格式提示词，可直接接入 NewBie 模型。 |
| `text_out` | LLM 输出的 XML 代码块以外的额外说明信息（通常为中文翻译）。 |

**内置鲁棒性机制：**

- **自动重试**：遇到网络抖动或 API 报错时，最多自动重试 3 次。
- **XML 自动修复**：使用 `lxml` 库对 LLM 输出的 XML 进行格式校验；若检测到格式错误，会自动修复并在控制台打印差异对比，大幅降低格式错误导致的流程中断。

**推荐模型（计价参考 [OpenRouter](https://openrouter.ai/)，均关闭思考模式）：**

| 模型名称 | 平均每次成本/美元 | NSFW 效果 | 输出质量 | 备注 |
|----------|-----------------|-----------|----------|------|
| `deepseek/deepseek-v3.2` | ~0.0008 | 均衡 | 均衡 | 综合性价比高 |
| `google/gemini-3-flash-preview` | ~0.0035 | 较好（G 向需技巧） | 最好 | NewBie 训练打标模型之一 |
| `x-ai/grok-4.1-fast` | ~0.0007 | 最好 | 较好 | NewBie 训练打标模型之一 |
| `xiaomi/mimo-v2-flash` | ~0.0004 | 较好 | 一般 | — |
| `cognitivecomputations/dolphin-mistral-24b-venice-edition:free` | 免费 | 官方宣称无审查 | 较差 | — |

> **思考模式说明：** 目前仅适配了 OpenRouter、DeepSeek、小米 MIMO 和 Gemini 官方平台。其他平台请通过模型名称控制（如用 `deepseek-chat` 代替 `deepseek-reasoner`）。
>
> **开发者建议：**
>
> - 强烈建议关闭思考模式。关闭时每次约消耗 3000–4000 tokens；开启时可能消耗 5000–10000 tokens，且关闭思考有时反而能提升 NSFW 效果。
> - 不建议使用参数量不远高于 4B 的模型。NewBie 本身已内置 Gemma3 4B，使用同等量级的外部 LLM 意义不大。
>
> **免费额度提示：** 在 [DeepSeek 开放平台](https://platform.deepseek.com) 注册后可获赠 10 元免费额度，大约可使用 1000 次。

**进阶用法 (Few-Shot)**：

1.2.3 版本起，你可以在 `LPF_config.json` 中配置 `fewshot_user` 和 `fewshot_assistant` 字段，为 LLM 注入一轮前置对话上下文，用于定向增强模型在特定领域的表现。

<details open>
<summary>节点示例输入输出</summary>
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

**`text_out` 示例输出：**

```
画面描绘了一个未来科幻风格的指挥中心，充满全息显示屏和战术地图的蓝光投影。左侧是一位金发双马尾的萝莉指挥官，穿着短和服配红色腰带，戴着耳机正在专注地指挥战斗……
```

**图片示例输入：**

![](https://akizukipic.oss-cn-beijing.aliyuncs.com/img/202512252130733.png)

```
把图中的人物换成(white hair,high ponytail,white serafuku,short sleeves,short skirt,shirt tucked in,jacket,knee pads,elbow pads,fingerless_gloves,white legwear,kneehighs,high-top hiking sneakers,sidelocks,small breasts,shorts under skirt)
```

**图片示例输出：**

```xml
You are an assistant designed to generate high-quality anime images with the highest degree of image-text alignment based on xml format textual prompts. <Prompt Start>

<img>
 <character_1>
 <n>original_character</n>
 <gender>1girl</gender>
 <appearance>white_hair, high_ponytail, sidelocks, small_breasts, yellow_eyes, long_hair</appearance>
 <clothing>white_serafuku, short_sleeves, short_skirt, shirt_tucked_in, jacket, knee_pads, elbow_pads, fingerless_gloves, white_legwear, kneehighs, high-top_hiking_sneakers, shorts_under_skirt</clothing>
 <expression>thoughtful, focused</expression>
 <action>sitting, writing, holding_pen, leaning_forward</action>
 <position>center</position>
 </character_1>

 <general_tags>
 <count>1girl, solo</count>
 <style>anime_style, realistic_shading</style>
 <background>indoor, library, bookshelves, wooden_desk, wooden_chair, window, cherry_blossoms_outside_window, books_on_desk</background>
 <atmosphere>serene, evening</atmosphere>
 <quality>very_aesthetic, masterpiece, no_text</quality>
 <resolution>max_high_resolution</resolution>
 <artist>rella, maccha_(mochancc), tidsean, wlop, ciloranko, atdan, year_2024</artist>
 <objects>lamp, desk_lamp, stack_of_books, pen</objects>
 <other>from_side, detailed_background</other>
 </general_tags>

 <caption>A girl with white hair in a high ponytail and sidelocks sits thoughtfully at a wooden desk in a cozy library room during evening...</caption>
</img>
```

![](https://akizukipic.oss-cn-beijing.aliyuncs.com/img/202512252157926.png)

</details>

---

### 2. XML Style Injector

**功能：** 替换 `xml` 格式提示词中的 `<artist>` 和 `<style>` 风格信息，实现快速切换画风预设。

![image-20260113123426220](https://akizukipic.oss-cn-beijing.aliyuncs.com/img/202601131234704.png)

**输入参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `xml_input` | STRING | 待处理的 `xml` 格式提示词文本（通常来自 LLM Xml Prompt Formatter 的 `xml_out` 输出）。 |
| `preset` | 下拉框 | 选择预设风格提示词集合，内容来自 `LPF_config.json` 的 `styles` 字段。 |
| `artist_add` | STRING（可选） | 额外的画师标签，将**拼接在预设画师列表之前**。 |
| `style_add` | STRING（可选） | 额外的风格标签，将**拼接在预设风格列表之前**。 |

**输出参数：**

| 参数 | 说明 |
|------|------|
| `xml_output` | 注入风格后的 `xml` 格式提示词。 |

**使用说明：** 节点会查找 XML 中的 `<artist>` 和 `<style>` 标签并替换为选定预设的内容。若 XML 中不存在对应标签，节点会尝试在 `<general_tags>` 容器下创建。配置文件内置约 40 个预设风格串，可在[此链接](https://docs.qq.com/sheet/DTUNCQW5TWFBMVGhY?tab=BB08J2)查看例图。

<details open>
<summary>节点示例输入输出</summary>

示例输入：选择预设 `飘渺杰作光影集`，在 `artist_add` 中填写 `daito, kataokasan`

**示例输出：**

```xml
<img>
  ...
  <general_tags>
  <count>2girls</count>
  <style>**ultimate masterpiece digital painting**, **ethereal lighting**, **dreamy aesthetic**, ...</style>
  <artist>kataokasan, daito, pottsness, midori_fufu, kazutake_hazano, ...</artist>
  ...
  </general_tags>
  ...
</img>
```

**最终生成的图片：**

![图片示例](https://raw.githubusercontent.com/SuzumiyaAkizuki/image/main/ComfyUI_00221_.png)

</details>

---

### 3. Style Preset Saver

**功能：** 从当前提示词中自动提取 `<artist>` 和 `<style>` 标签，并将其保存为新的风格预设到 `LPF_config.json` 中，方便后续在 XML Style Injector 中调用。

![image-20260113123613316](https://akizukipic.oss-cn-beijing.aliyuncs.com/img/202601131236975.png)

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
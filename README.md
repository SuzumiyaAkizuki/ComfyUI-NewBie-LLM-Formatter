# ComfyUI-NewBie-LLM-Formatter

[![ComfyUI](https://img.shields.io/badge/ComfyUI-Compatible-green.svg)](https://comfy.org/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![NewBie](https://img.shields.io/badge/NewBie-Compatible-yellow.svg)](https://huggingface.co/NewBie-AI/NewBie-image-Exp0.1)

使用LLM API自动生成适用于NewBie模型的XML风格提示词，并调整画面风格

## 更新说明

<details>
<summary> 更新说明 </summary>

### 2026年01月12日更新1.1.7

 - 极大提升**「非Gemini官方平台」**Gemini模型的NSFW能力，可以完成一般的NSFW书写。如果仍然不能破甲（多见于G向），可以尝试在敏感提示词中间加入字符以破坏token，例如`blood -> blo···od`。

   即使如此，仍然不能绝对成功，如果失败可以多尝试几次，或者删掉部分提示词，比如`loli`。

 - 优化了「思考模型开关」的逻辑，支持Gemini官方平台。而且，如果遇到不支持的平台，将不再报错。

 - 更新了示例工作流。

   > *开发者笔记：Gemini官方平台的API加上强力破限词以后，反而什么都不输出了。而且，我使用了不同的API中转平台，破限能力也有差异，其中，[OpenRouter](https://openrouter.ai/)的破限效果是最好的。总之，我在破限方面的努力就到此为止了。NewBie模型是用gemini和grok打的标签训练的，所以我也只做了gemini的破限。关于思考模式，各家平台的标准都不甚统一，所以我只做了最大的API中转平台[OpenRouter](https://openrouter.ai/)和两个常用官方平台（Deepseek、Gemini）的支持。*

### 2026年01月08日更新1.1.6

- Style Preset Saver增加一个输出流，可以预览将要保存的风格提示词组
- 解决了一部分bug，优化了用户引导

### 2026年01月07日更新1.1.5

- 增加Style Preset Saver节点，现在可以将自定义风格提示词组保存在配置文件中
- LLM Xml Prompt Formatter 增加一个按钮，可以选择是否开启模型的思考模式。思考内容在控制台输出
- LLM Xml Prompt Formatter 将会在控制台输出本次请求消耗的 tokens 数量
- 更新更多预设风格提示词组
- 更新ReadMe文档，增加大模型评测

### 2026年01月03日更新1.1.0

- 更新更多预设风格提示词组
- 增添`requirements.txt`文件，可以自动安装依赖

### 2025年12月26日更新1.0.7

- LLM Xml Prompt Formatter增加一个可选输入流，图片格式。如果你使用多模态大模型，那么可以输入图片。
- 更新了system prompt，更节约tokens

### 2025年12月24日更新1.0.5

 - 修改提示词结构，现在提示词严格按照xml格式生成
 - 在LLM输出后进行xml格式检查与修复，降低格式错误可能性
 - 将原先的正则表达式匹配法改为使用解析xml的方法进行数据清洗和标签注入，增强程序鲁棒性
 - 增添依赖[lxml](https://github.com/lxml/lxml)

### 2025年12月22日更新1.0.0
 - 修改文件结构，所有节点的配置均统合在`LPF_config.json`中
 - 发送原图不再暴露你的API KEY
 - 增添`json`文件编辑小工具
 - 修改了默认system prompt，节约tokens
 - 增添了LLM输出清洗流程，增强程序鲁棒性

</details>




## 节点说明

ComfyUI-NewBie-LLM-Formatter提供三个节点：

1. LLM Xml Prompt Formatter

   **功能：** 将用户输入的自然语言或标签集格式化为`xml`格式，供NewBie模型使用。

   **输入参数：** 一个可选图片输入流，四个文本输入框，一个按钮，分别是：

   - `image`：可选，将输入的图片传输给LLM。请注意，这只是让LLM反推提示词，不是传统意义上的图生图。

   - `api_key`：Open AI格式大模型`api_key`

   - `api_url`：API主机地址

   - `model_name`：模型名称

   - `thinking`：深度思考模式。显示`true`时，模型将进行深度思考，思考过程将在控制台显示。显示`false`时，模型不进行深度思考。推荐将其设置为`false`。

     > 目前，仅适配了OpenRouter平台和deepseek平台。部分平台不支持设置此字段，请用模型名称控制。
     >
     > 例如，可以使用`deepseek-chat`来使用无思考的deepseek，使用`deepseek-reasoner`来使用有思考的deepseek。

   - 待转换文本

   **输出参数：** 2个文本格式输出流

   - `xml_out`：`xml`格式提示词
   - `text_out`：大模型输出的额外解释信息

   **使用说明：** 使用前，请先在`LPF_config.json`中填写API key、API url和模型名称。`LPF_config.json` 中的 `system_prompt` 字段为大模型使用的预设提示词，其中内置基本破限命令。以下是推荐的模型：

   | 模型名称                    | 平均每次使用成本/美元 | NSFW效果 | 输出质量 | 备注 |
   | --------------------------- | --------------------- | ------------ | --------------------------- | --------------------------- |
   | `deepseek/deepseek-v3.2` | 0.0008              | 均衡 | 均衡 | 均衡 |
   | `google/gemini-3-flash-preview` | 0.0035              | 较好，部分情况(G向)仍需技巧 | 最好 |  |
   | `x-ai/grok-4.1-fast` | 0.0007              | 最好 | 较好 |  |
   | `xiaomi/mimo-v2-flash:free` | 0（免费） | 较好 | 一般 |  |
   | `cognitivecomputations/dolphin-mistral-24b-venice-edition:free` | 0（免费） | 官方宣称无审查 | 较差 |  |

   > 计价参考平台为[OpenRouter](https://openrouter.ai/)，所有模型均关闭思考模式，评测为个人使用体感，仅供参考。
   >
   > 强烈建议在使用时关闭思考模式，这会大大降低耗时、减小 token 消耗（关闭思考模式一次使用大约消耗 3000-4000 tokens ，开启思考模式可能会消耗 5000 甚至 10000 tokens）。此外，关闭思考模式有可能还会提升NSFW效果。

   在[Deepseek开放平台](https://platform.deepseek.com)上，每位用户可以获赠10元的免费额度，大约可以使用1000次。

<details>
<summary> 节点示例输入输出 </summary>


   **纯文本示例输入：**

   ```
   A:(loli,(blonde hair:1.2),hair between eyes,short hair,ahoge,twintails,short tail,short_kimono,white socks,Frilled socks,converse,sash,red_sash,sidelocks,low twintails, fingerless gloves, haori,shorts under skirt,hairclip,leg belt)
   
   B:(white hair,high ponytail,white serafuku,short sleeves,short skirt,shirt tucked in,knee pads,elbow pads,fingerless gloves,white legwear,kneehighs,high-top hiking sneakers,sidelocks,shorts under skirt,)
   
   在一个科幻风格的指挥所中，画面左侧，A担任一场战役的指挥官。她戴着耳麦，正在指挥战役。指挥所里有全息显示的显示屏和地图。画面右侧，B穿着战术马甲、戴着头盔、拿着狙击步枪，正在执行作战任务。这两个场景的画面要有机地融合在一起，动漫风格、油画风格。
   ```

   **纯文本示例输出：**

   `xml_out`：

   ```xml
   You are the greatest anime artist in the entire universe. Your figures are always clear, especially in facial detail. Your compositions always adhere to the golden ratio. Your perspectives are perfectly chosen. The scenes in your works always fit the setting. Your lighting is particularly atmospheric.Now draw a picture based on the prompts below.You are an assistant designed to generate anime images based on xml format textual prompts.  <Prompt Start>
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
     <style>anime_style, oil_painting_style</style>
     <background>sci-fi_command_center, holographic_displays, tactical_map, futuristic_technology</background>
     <atmosphere>tense, strategic</atmosphere>
     <lighting>dramatic_lighting, neon_glow</lighting>
     <quality>very_aesthetic, masterpiece, no_text</quality>
     <resolution>max_high_resolution</resolution>
     <artist>rella,maccha_\(mochancc\),tidsean,wlop,ciloranko,atdan,year 2024</artist>
     <objects>headset, sniper_rifle, tactical_gear, holograms</objects>
     </general_tags>
     
     <caption>In a futuristic sci-fi command center with glowing holographic displays and tactical maps, two girls are shown in different roles. On the left side, a blonde loli girl with short twintails and an ahoge wears a short kimono with a red sash, fingerless gloves, and converse shoes. She's wearing a headset and intensely pointing at holographic projections while commanding a battle. On the right side, a white-haired girl in a white serafuku uniform with tactical vest and helmet holds a sniper rifle in combat stance, wearing knee pads and hiking sneakers. The two scenes are seamlessly blended together with dramatic neon lighting casting blue and orange hues across the high-tech environment.</caption>
   </img>
   ```

   `text_out`：

   ```
   画面描绘了一个未来科幻风格的指挥中心，充满全息显示屏和战术地图的蓝光投影。左侧是一位金发双马尾的萝莉指挥官，穿着短和服配红色腰带，戴着耳机正在专注地指挥战斗，手指指向全息投影。右侧是一位白发高马尾的少女，穿着白色水手服搭配战术背心和头盔，手持狙击步枪处于战斗姿态，膝盖和手肘都戴着护具。两个场景通过戏剧性的霓虹灯光效完美融合，蓝橙相间的光线在高科技环境中交织。指挥中心的未来感装备与两位少女的不同战斗角色形成鲜明对比。
   ```

   **图片示例输入：**

   ![](https://akizukipic.oss-cn-beijing.aliyuncs.com/img/202512252130733.png)

   ```
   把图中的人物换成(white hair,high ponytail,white serafuku,short sleeves,short skirt,shirt tucked in,jacket,knee pads,elbow pads,fingerless_gloves,white legwear,kneehighs,high-top hiking sneakers,sidelocks,small breasts,shorts under skirt),
   ```

   **图片示例输出：**

   ```xml
   You are the greatest anime artist in the entire universe. Your figures are always clear, especially in facial detail. Your compositions always adhere to the golden ratio. Your perspectives are perfectly chosen. The scenes in your works always fit the setting. Your lighting is particularly atmospheric.Now draw a picture based on the prompts below.You are an assistant designed to generate anime images based on xml format textual prompts.  <Prompt Start>
   
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
    
    <caption>A girl with white hair in a high ponytail and sidelocks sits thoughtfully at a wooden desk in a cozy library room during evening, focused on writing with a pen in hand, leaning slightly forward. She has small breasts and wears a white serafuku with short sleeves, shirt tucked in, a jacket, knee pads, elbow pads, fingerless gloves, white kneehighs, high-top hiking sneakers, and shorts under her short skirt. The room features tall bookshelves filled with books, a wooden chair, and a large window showing cherry blossoms in bloom outside under a twilight sky, with a warm desk lamp casting soft golden light and subtle shadows across the desk, books, and her figure, enhancing the serene atmosphere.</caption>
   </img>
   ```

   ```
   一个留着高马尾和侧发的白发女孩在黄昏时分的温馨图书馆房间里，若有所思地坐在木桌前，专注地用笔书写，微微前倾身体。她胸部娇小，穿着白色水手服短袖，上衣塞进短裙，配外套、护膝、护肘、无指手套、白色及膝袜、高帮登山鞋，以及裙下短裤。房间里有高大的书架堆满书籍、木椅和大窗户，窗外是盛开的樱花树在暮色天空下，一盏温暖的台灯投下柔和的金色光芒和细微阴影，照亮桌面、书籍和她的身影，营造出宁静氛围。
   ```

   ![](https://akizukipic.oss-cn-beijing.aliyuncs.com/img/202512252157926.png)

</details>


2. Xml Style Injecto

   **功能：** 替换`xml`格式提示词中的风格信息

   **输入参数：** 1个文本格式输入流，1个下拉选项框，2个文本输入框

   - `xml_input`：待处理的`xml`格式文本
   - `preset`：下拉选项框，可以在此处选择预设风格提示词集合
   - `artist`：文本输入框，将输入的画师信息添加在预设风格提示词集合的前方
   - `style`：文本输入框，将输入的风格信息添加在预设风格提示词集合的前方

   **输出参数：** 1个文本格式输出流

   - `xml_output`：处理后的`xml`格式提示词

   **使用说明：** `LPF_config.json` 中的 `style` 字段为为预设风格提示词集合，你可以通过修改这个文件来添加风格提示词串。

<details>
<summary> 节点示例输入输出 </summary>

   示例输入：选择`飘渺杰作光影集`，增加`artist`：`daito,kataokasan`

   **示例输出：**

   ```xml
   You are the greatest anime artist in the entire universe. Your figures are always clear, especially in facial detail. Your compositions always adhere to the golden ratio. Your perspectives are perfectly chosen. The scenes in your works always fit the setting. Your lighting is particularly atmospheric.Now draw a picture based on the prompts below.You are an assistant designed to generate anime images based on xml format textual prompts.  <Prompt Start>
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
     <style>**ultimate masterpiece digital painting**, **ethereal lighting**, **dreamy aesthetic**, **delicate floral details**, **high saturation blue sky**, **expressionist brushwork and high textural detail**, **maximalist detail**, **painterly texture**, oil painting, stunning aesthetic, ultra-detailed cross-hatching, extreme high contrast, dynamic line art</style>
     <background>sci-fi_command_center, holographic_displays, tactical_map, futuristic_technology</background>
     <atmosphere>tense, strategic</atmosphere>
     <lighting>dramatic_lighting, neon_glow</lighting>
     <quality>very_aesthetic, masterpiece, no_text</quality>
     <resolution>max_high_resolution</resolution>
     <artist>kataokasan,daito, pottsness, midori_fufu, kazutake_hazano, sushispin, rella, konya_karasue, void_0, (wanke:0.4), (blackbeat:0.4), (JUEJUE:0.5), (Ebor18:1.2)</artist>
     <objects>headset, sniper_rifle, tactical_gear, holograms</objects>
     </general_tags>
     
       <caption>In a futuristic sci-fi command center with glowing holographic displays and tactical maps, two girls are shown in different roles. On the left side, a blonde loli girl with short twintails and an ahoge wears a short kimono with a red sash, fingerless gloves, and converse shoes. She's wearing a headset and intensely pointing at holographic projections while commanding a battle. On the right side, a white-haired girl in a white serafuku uniform with tactical vest and helmet holds a sniper rifle in combat stance, wearing knee pads and hiking sneakers. The two scenes are seamlessly blended together with dramatic neon lighting casting blue and orange hues across the high-tech environment.</caption>
   </img>
   ```

   **最终生成的图片：**

   ![图片示例](https://raw.githubusercontent.com/SuzumiyaAkizuki/image/main/ComfyUI_00221_.png)

</details>


3. Style Preset Saver

   **功能**：将目前使用的风格提示词组保存在配置文件`LPF_config.json`中。

   **输入参数**：1个文本格式输入流，1个单行文本框，1个按钮

   - `text_input`：文本格式输入流，输入目前使用的提示词，节点将自动解析其中的`<artist>`和`<style>`字段。
   - `preset_name`：单行文本框，保存预设的名称。如果遇到重名或空名称，节点将放弃保存。
   - `save_tigger`：按钮，只有显示`Save as Styles`时，才会进行保存。

   **输出参数**：1个文本格式输出流

   - `extracted_tags`：预览将要保存的风格提示词组列表

   

## 依赖

请参考项目中的`requirements.txt`

## 参考工作流

保存在项目的`NewBie_LLM_Formatter_example.json`中。右键另存为，打开Comfy-UI，按<kbd>Ctrl</kbd>+<kbd>O</kbd>，选择此文件，即可加载示例工作流。

此工作流是一个完整、成熟的工作流，里面有其他的节点，但是我写了详细的注释。


## 安装和使用方法

点击Github页面中绿色按钮`<>Code`，点击Download ZIP，将会下载一个压缩包。

![下载按钮](https://akizukipic.oss-cn-beijing.aliyuncs.com/img/202512211546384.png)

![压缩包](https://akizukipic.oss-cn-beijing.aliyuncs.com/img/202512211548632.png)

将该文件夹放置在`...\ComfyUI\custom_nodes\`目录下

![image-20251226145335813](https://akizukipic.oss-cn-beijing.aliyuncs.com/img/202512261453308.png)

进入文件夹，找到`LPF_config.json.example`文件，右键重命名，删掉`.example`后缀

![重命名前](https://akizukipic.oss-cn-beijing.aliyuncs.com/img/202512261454909.png)

删完就像这样

![image-20251226145521692](https://akizukipic.oss-cn-beijing.aliyuncs.com/img/202512261455772.png)

使用记事本或文件编辑器打开此文件，在对应的字段中填写你的api_key

![填写前后对比](https://akizukipic.oss-cn-beijing.aliyuncs.com/img/202512261457930.png)

重启Comfy-UI，即可使用。












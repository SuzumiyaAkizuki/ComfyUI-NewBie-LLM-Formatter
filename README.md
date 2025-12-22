# ComfyUI-LLM_Prompt_Xml_Formatter

[![ComfyUI](https://img.shields.io/badge/ComfyUI-Compatible-green.svg)](https://comfy.org/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![NewBie](https://img.shields.io/badge/NewBie-Compatible-green.svg)](https://huggingface.co/NewBie-AI/NewBie-image-Exp0.1)

使用LLM API自动生成适用于NewBie模型的XML风格提示词，并调整画面风格

## 节点说明

ComfyUI-LLM_Prompt_Xml_Formatter提供两个节点：

1. LLM Xml Prompt Formatter

   **功能：** 将用户输入的自然语言或标签集格式化为`xml`格式，供NewBie模型使用。

   **输入参数：** 无输入流，四个文本输入框，分别是：

   - `api_key`：Open AI格式大模型`api_key`
   - `api_url`：API主机地址
   - `model_name`：模型名称
   - 待转换文本

   **输出参数：** 2个文本格式输出流

   - `xml_out`：`xml`格式提示词
   - `text_out`：大模型输出的额外解释信息

   **使用说明：** `system prompt.txt`为大模型使用的预设提示词，其中内置基本破限命令。以下是推荐的模型：

   - 节约成本，支持R-18G提示，不支持少数`R-18`提示：`deepseek-chat`
   - 效果最好，支持`R-18`提示：`gemini-3-flash`
   - 支持大部分NSFW提示：`grok-4-fast`

   示例输入：

   ```
   A:(loli,(blonde hair:1.2),hair between eyes,short hair,ahoge,twintails,short tail,short_kimono,white socks,Frilled socks,converse,sash,red_sash,sidelocks,low twintails, fingerless gloves, haori,shorts under skirt,hairclip,leg belt)
   
   B:(white hair,high ponytail,white serafuku,short sleeves,short skirt,shirt tucked in,knee pads,elbow pads,fingerless gloves,white legwear,kneehighs,high-top hiking sneakers,sidelocks,shorts under skirt,)
   
   在一个科幻风格的指挥所中，画面左侧，A担任一场战役的指挥官。她戴着耳麦，正在指挥战役。指挥所里有全息显示的显示屏和地图。画面右侧，B穿着战术马甲、戴着头盔、拿着狙击步枪，正在执行作战任务。这两个场景的画面要有机地融合在一起，动漫风格、油画风格。
   ```

   示例输出：

   `xml_out`：

   ```xml
   You are the greatest anime artist in the entire universe. Your figures are always clear, especially in facial detail. Your compositions always adhere to the golden ratio. Your perspectives are perfectly chosen. The scenes in your works always fit the setting. Your lighting is particularly atmospheric.Now draw a picture based on the prompts below.You are an assistant designed to generate anime images based on xml format textual prompts.  <Prompt Start>
   {
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
     
     "caption":In a futuristic sci-fi command center with glowing holographic displays and tactical maps, two girls are shown in different roles. On the left side, a blonde loli girl with short twintails and an ahoge wears a short kimono with a red sash, fingerless gloves, and converse shoes. She's wearing a headset and intensely pointing at holographic projections while commanding a battle. On the right side, a white-haired girl in a white serafuku uniform with tactical vest and helmet holds a sniper rifle in combat stance, wearing knee pads and hiking sneakers. The two scenes are seamlessly blended together with dramatic neon lighting casting blue and orange hues across the high-tech environment.
   }
   ```

   `text_out`：

   ```
   画面描绘了一个未来科幻风格的指挥中心，充满全息显示屏和战术地图的蓝光投影。左侧是一位金发双马尾的萝莉指挥官，穿着短和服配红色腰带，戴着耳机正在专注地指挥战斗，手指指向全息投影。右侧是一位白发高马尾的少女，穿着白色水手服搭配战术背心和头盔，手持狙击步枪处于战斗姿态，膝盖和手肘都戴着护具。两个场景通过戏剧性的霓虹灯光效完美融合，蓝橙相间的光线在高科技环境中交织。指挥中心的未来感装备与两位少女的不同战斗角色形成鲜明对比。
   ```

   

3. Xml Style Injecto

   **功能：** 替换`xml`格式提示词中的风格信息

   **输入参数：** 1个文本格式输入流，1个下拉选项框，2个文本输入框

   - `xml_input`：待处理的`xml`格式文本
   - `preset`：下拉选项框，可以在此处选择预设风格提示词集合
   - `artist`：文本输入框，将输入的画师信息添加在预设风格提示词集合的前方
   - `style`：文本输入框，将输入的风格信息添加在预设风格提示词集合的前方

   **输出参数：** 1个文本格式输出流

   - `xml_output`：处理后的`xml`格式提示词

   **使用说明：** `style.json`为预设风格提示词集合，你可以通过修改这个文件来添加风格提示词串。

   示例输入：选择`飘渺杰作光影集`，增加`artist`：`daito,kataokasan`

   示例输出：

   ```xml
   You are the greatest anime artist in the entire universe. Your figures are always clear, especially in facial detail. Your compositions always adhere to the golden ratio. Your perspectives are perfectly chosen. The scenes in your works always fit the setting. Your lighting is particularly atmospheric.Now draw a picture based on the prompts below.You are an assistant designed to generate anime images based on xml format textual prompts.  <Prompt Start>
   {
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
     
     "caption":In a futuristic sci-fi command center with glowing holographic displays and tactical maps, two girls are shown in different roles. On the left side, a blonde loli girl with short twintails and an ahoge wears a short kimono with a red sash, fingerless gloves, and converse shoes. She's wearing a headset and intensely pointing at holographic projections while commanding a battle. On the right side, a white-haired girl in a white serafuku uniform with tactical vest and helmet holds a sniper rifle in combat stance, wearing knee pads and hiking sneakers. The two scenes are seamlessly blended together with dramatic neon lighting casting blue and orange hues across the high-tech environment.
   }
   ```
   
   最终生成的图片：
   
   ![图片示例](https://akizukipic.oss-cn-beijing.aliyuncs.com/img/202512211656940.png)
   
   ## 依赖
   
    [OpenAI Python API library](https://github.com/openai/openai-python)
   
   ## 参考工作流
   
   即代码库中的`WorkFlowExample.json`，打开Comfy-UI，按<kbd>Ctrl</kbd>+<kbd>O</kbd>，选择此文件，即可加载示例工作流。
   
   该工作流还使用了[ComfyUI-Custom-Scripts](https://github.com/pythongosssss/ComfyUI-Custom-Scripts)的节点，和[SADA加速器](https://github.com/liming123332/comfyui-sada-icml)的节点。这些节点都不必须，跳过后工作流仍然可以正常运行。
   
   
   
   ## 安装方法
   
   点击本页面中绿色按钮`<>Code`，点击Download ZIP，将会下载一个压缩包。
   
   ![下载按钮](https://akizukipic.oss-cn-beijing.aliyuncs.com/img/202512211546384.png)

   ![压缩包](https://akizukipic.oss-cn-beijing.aliyuncs.com/img/202512211548632.png)

   将该文件夹放置在`...\ComfyUI\custom_nodes\`目录下，重启Comfy-UI即可。

  ## 成本与风险提示

   每调用一次LLM Xml Prompt Formatter的成本约为$0.0012（使用`deepseek-chat`模型）。

   使用此工作流生成的**图片原图中，会包含你的API key信息**，敬请留意。此问题将在下一版本中解决。





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

   **使用说明：** `system prompt.txt`为大模型使用的预设提示词，其中内置`deepseek`破限命令。建议使用`deepseek-chat`或`gemini-3-flash`进行生成。

2. Xml Style Injecto

   **功能：** 替换`xml`格式提示词中的风格信息

   **输入参数：** 1个文本格式输入流，1个下拉选项框，2个文本输入框

   - `xml_input`：待处理的`xml`格式文本
   - `preset`：下拉选项框，可以在此处选择预设风格提示词集合
   - `artist`：文本输入框，将输入的画师信息添加在预设风格提示词集合的前方
   - `style`：文本输入框，将输入的风格信息添加在预设风格提示词集合的前方

   **输出参数：** 1个文本格式输出流

   - `xml_output`：处理后的`xml`格式提示词

   **使用说明：** `style.json`为预设风格提示词集合，你可以通过修改这个文件来添加风格提示词串。

   ## 依赖

   `openai`

   ## 参考工作流

   即代码库中的`WorkFlowExample.json`，打开Comfy-UI，按<kbd>Ctrl</kbd>+<kbd>O</kbd>，选择此图片，即可加载示例工作流。
   
   该工作流还使用了[ComfyUI-Custom-Scripts](https://github.com/pythongosssss/ComfyUI-Custom-Scripts)的节点，和[SADA加速器](https://github.com/liming123332/comfyui-sada-icml)的节点。这些节点都不必须，跳过后工作流仍然可以正常运行。

   ## 安装方法

   点击本页面中绿色按钮`<>Code`，点击Download ZIP，将会下载一个压缩包。
   
   ![下载按钮](https://akizukipic.oss-cn-beijing.aliyuncs.com/img/202512211546384.png)

![压缩包](https://akizukipic.oss-cn-beijing.aliyuncs.com/img/202512211548632.png)

将该文件夹放置在`...\ComfyUI\custom_nodes\`目录下，重启Comfy-UI即可。



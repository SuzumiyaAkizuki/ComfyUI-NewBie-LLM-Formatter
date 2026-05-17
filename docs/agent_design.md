# LLM_Prompt_Formatter Agent 化改造设计文档

> 版本：v1.0 | 日期：2026-05-15

## 1. 概述

### 目标

将 `LLM_Prompt_Formatter` 节点从"单轮 LLM 调用"升级为"Agent 循环"模式，使其能够在生成提示词的过程中自动调用 Danbooru 标签搜索工具（MCP Server），获取精确标签而非完全依赖 LLM 记忆。

### 背景

当前项目的 `LLM_Prompt_Formatter` 节点直接将用户输入交给 LLM 生成提示词。用户已有两个相关项目：

- **Danbooru MCP Server** — 部署在 HuggingFace Space 上的 MCP 服务，提供 `search_tags` 和 `get_related_tags` 两个工具
- **问秋月 Agent** — 网页版问答 Agent，已实现完整的多轮 Tool Calling 循环

本次改造复用这两个项目的基础设施，在 ComfyUI 节点中实现同等的 Agent 能力。

### 范围

仅改造 `LLM_Prompt_Formatter` 节点。`LLM_Xml_Style_Injector` 和 `Style_Saver` 保持不变。

---

## 2. 架构设计

### 文件结构

```
ComfyUI-NewBie-LLM-Formatter/
├── LLM_Node.py              # 修改：新增 agent_mode 开关和 mcp_url 输入
├── LLM_Style_Node.py        # 不变
├── Style_Saver_Node.py      # 不变
├── __init__.py              # 不变
├── requirements.txt         # 修改：新增 httpx 依赖
├── prompt_agent/            # 新增目录
│   ├── __init__.py          # 包初始化
│   ├── agent_core.py        # PromptAgent 类 — 完整 Agent 循环
│   ├── tools.py             # MCP 通信层 — 从问秋月项目复用
│   └── agent_prompts.py     # Agent 模式专用系统提示词
└── docs/
    └── agent_design.md      # 本文档
```

### 数据流

```
当前（无 Agent）:
  user_text → LLM API → 解析输出 → xml_out / text_out

Agent 模式:
  user_text → 查询重写 → [LLM + Tool Calling 循环] → 解析输出 → xml_out / text_out
                              ↕                    ↕
                         search_tags          get_related_tags
                              ↕                    ↕
                         MCP Server (HTTP)
```

---

## 3. 节点接口变更

### 新增输入参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `agent_mode` | BOOLEAN | Agent 模式开关，默认 `False`。开启后启用完整 Tool Calling 循环。 |

MCP Server 地址硬编码在 `tools.py` 中（双端点：HF + MS），不在 UI 上暴露。

### 现有参数

全部保持不变：`api_key`、`api_url`、`model_name`、`user_text`、`thinking`、`mode`、`image`。

### 输出

不变：`xml_out` 和 `text_out` 两个 STRING 输出，下游节点无需任何适配。

### 行为矩阵

| agent_mode | mode | 行为 |
|------------|------|------|
| False | NewBie | 当前行为不变：单轮 LLM → XML 输出 |
| False | Anima | 当前行为不变：单轮 LLM → 纯文本输出 |
| True | NewBie | Agent 循环 → 最终以 NewBie XML 格式输出 |
| True | Anima | Agent 循环 → 最终以 Anima 纯文本格式输出 |

---

## 4. Agent 核心循环 (`agent_core.py`)

### PromptAgent 类接口

```python
class PromptAgent:
    def __init__(self, api_key, api_url, model_name, mode, thinking):
        ...

    def run(self, user_text, image=None) -> tuple[str, str]:
        """执行完整 Agent 循环，返回 (xml_out, text_out)"""
```

### 循环流程

```
1. 构建系统提示词（含工具描述 + 模式指令）
2. 构建用户消息（XML 标签包裹 + 可选图片）
3. 查询重写（首轮时，用 LLM 将用户输入拆解为 3~5 个搜索维度）
4. 进入多轮循环（最多 MAX_ROUNDS = 10）：
   a. 调用 LLM（stream=True，带 tools 定义）
   b. 如果 finish_reason == "tool_calls"：
      - 解析工具调用参数
      - 执行工具（search_tags / get_related_tags）
      - 将结果追加到 messages
      - 继续循环
   c. 如果 finish_reason == "stop"：
      - 退出循环，拿到最终回答
5. 解析最终回答（复用现有 clean_prompt / split_by_language 逻辑）
6. 返回 (xml_out, text_out)
```

### 与问秋月 Agent 的差异

| 方面 | 问秋月 Agent | PromptAgent |
|------|-------------|-------------|
| 流式输出 | 实时 token 流式输出到网页 | 不流式输出到 UI，但 Log 打印过程 |
| 系统提示词 | 问答助手身份 + 标签搜索规则 | 提示词生成专家身份 + 搜索→生成流程 |
| 输出解析 | 直接返回文本 | 需要走 clean_prompt / split_by_language |
| 查询重写 | 画面要素分解 | 同样逻辑，复用 QUERY_REWRITE_PROMPT |
| 错误处理 | 返回 error SSE 事件 | 抛出异常，由节点捕获并重试 |

---

## 5. 工具层 (`tools.py`)

从问秋月项目直接复用，不做修改。核心功能：

- `TOOLS` — 工具定义列表（OpenAI function calling 格式），模块加载时从 MCP Server 动态拉取，失败时回退到内置定义
- `execute_search_tags(query, ...)` — 调用 MCP Server 的 `search_tags` 工具
- `execute_get_related_tags(tags, ...)` — 调用 MCP Server 的 `get_related_tags` 工具
- `_rpc(method, params)` — 底层 JSON-RPC 通信，含双端点自动切换
- `check_mcp_health()` — 健康检查（用于降级判断）

### MCP 通信协议

- 协议：Streamable HTTP（POST JSON-RPC，非 SSE）
- 握手：每次调用前执行 `initialize` 获取 session id（HF Space 多副本部署不复用 session）
- 双端点：HF Space (主) + MS Show (备)，自动切换
- 重试：429 限流时指数退避（5s → 10s → 20s，最多 3 次）

---

## 6. 系统提示词 (`agent_prompts.py`)

### Agent 系统提示词结构

```
# 身份
你是一个专业的文生图提示词格式化专家...

# 工具使用规则
1. 每轮回答前，必须先调用 search_tags 搜索标签，禁止凭记忆给标签
2. search_tags 之后可调用 get_related_tags 进行共现探索
3. 支持链式探索：search → related → search
4. 查询必须用中文

# 自主补全规则
当用户描述简略时，必须先在内部补全缺失维度再搜索

# 输出格式要求
根据当前 mode 选择输出格式（NewBie XML / Anima 纯文本）
```

### 与现有 system_prompt 的关系

- Agent 系统提示词是**独立于** `LPF_config.json` 中 `system_prompt` 的新提示词
- config 中的破限内容（`gemini_jailbreaker`）、few-shot 设置仍然会拼接
- 工具定义已在 `TOOLS` 中包含完整参数指南，系统提示词不重复

---

## 7. Log 输出设计

所有 Agent Log 统一用 `[Agent]` 前缀。

### 正常流程 Log

```
[Agent] ══════════════════════════════════════════════
[Agent] Agent 模式已启用，开始处理用户输入...
[Agent] 模式: NewBie | MCP: HF (主) / MS (备)
[Agent] ══════════════════════════════════════════════

[Agent] ── 查询重写 ──────────────────────────────────
[Agent] 用户输入拆解为 3 个搜索维度:
[Agent]   1. 皮夹克女孩短发机械义眼
[Agent]   2. 单手夹烟侧脸烟雾
[Agent]   3. 雨夜霓虹街道积水反光
[Agent] ───────────────────────────────────────────────

[Agent] ── Round 1 ──────────────────────────────────
[Agent] LLM 请求: 2 tools available
  > 搜索标签：皮夹克女孩短发机械义眼
    [search_tags] top_k=5, limit=80, segmentation=True
    找到 42 个标签
  > 搜索标签：雨夜霓虹街道积水反光
    [search_tags] top_k=5, limit=80, segmentation=True
    找到 38 个标签
[Agent] Token: 1200 input + 800 output = 2000 used
[Agent] ───────────────────────────────────────────────

[Agent] ── Round 2 ──────────────────────────────────
[Agent] LLM 请求: 2 tools available
  > 关联推荐：leather_jacket, short_hair, glowing_eye
    [get_related_tags] tags=3, limit=30
    找到 28 个标签
[Agent] Token: 2100 input + 600 output = 2700 used
[Agent] ───────────────────────────────────────────────

[Agent] ── Round 3 ──────────────────────────────────
[Agent] LLM 请求: 2 tools available
[Agent] LLM 输出最终回答 (finish_reason=stop)
[Agent] Token: 3500 input + 1200 output = 4700 used
[Agent] ───────────────────────────────────────────────

[Agent] ── 输出解析 ──────────────────────────────────
[Agent] NewBie 模式: 提取 XML 代码块
[Agent] XML 格式检查通过 ✓
[Agent] ───────────────────────────────────────────────

[Agent] ══════════════════════════════════════════════
[Agent] Agent 完成 | 总轮次: 3 | 总 Token: 9400
[Agent] ══════════════════════════════════════════════
```

### 异常 Log

```
[Agent] ⚠ MCP 服务连接超时，正在切换备用端点...
[Agent] ⚠ 搜索标签返回空结果，提示 LLM 改写查询
[Agent] ✗ Agent 循环超过最大轮次 (10)，强制输出
[Agent] ✗ MCP 服务不可用，回退为普通模式
```

---

## 8. 错误处理与降级策略

### 三层降级机制

**第一层：工具调用级重试**
- search_tags / get_related_tags 调用失败时自动重试 3 次（5s → 10s → 20s）
- 重试失败后返回错误 JSON 给 LLM，由 LLM 决定下一步

**第二层：MCP 端点级降级**
- tools.py 已有双端点自动切换（HF ↔ MS）
- 主端点不可用时自动切换备用端点

**第三层：Agent → 普通模式降级**
- MCP 服务完全不可用时，自动降级为普通模式
- Log 打印警告，节点不会报错

### Agent 循环异常处理

| 异常场景 | 处理方式 |
|---------|---------|
| LLM 返回格式错误 | 捕获异常，将错误信息作为 tool result 反馈给 LLM |
| LLM 陷入死循环 | 检测重复调用，超过 3 次强制退出循环 |
| 超过 MAX_ROUNDS (10) | 追加强制输出指令，再做最后一轮 |
| LLM API 报错 | 沿用现有重试逻辑（3 次），最终失败抛出 RuntimeError |
| 查询重写失败 | 跳过重写，直接用原始输入进入 Agent 循环 |

### 兼容性保障

- `agent_mode=False` 时，代码路径与现有完全一致
- 新增依赖 `httpx`，已在 `requirements.txt` 中声明
- MCP Server 不可达时不会阻塞节点
- MCP 地址硬编码在 `tools.py` 中，用户无需配置

---

## 9. 依赖变更

### requirements.txt

```
openai
lxml
numpy
Pillow
httpx
```

新增 `httpx`，用于 MCP Streamable HTTP 通信。

---

## 10. 实现计划概要

| 阶段 | 内容 | 涉及文件 |
|------|------|---------|
| 1 | 复制并适配 tools.py | `prompt_agent/tools.py`, `prompt_agent/__init__.py` |
| 2 | 编写 Agent 系统提示词 | `prompt_agent/agent_prompts.py` |
| 3 | 实现 PromptAgent 核心类 | `prompt_agent/agent_core.py` |
| 4 | 修改 LLM_Node.py 集成 Agent | `LLM_Node.py` |
| 5 | 更新 requirements.txt | `requirements.txt` |
| 6 | 测试验证 | 全部文件 |

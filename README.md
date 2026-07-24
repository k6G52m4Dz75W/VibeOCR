# VibeOCR 📖✨

> **智能端到端书籍 OCR 解决方案** — 多模型 AI 驱动，PDF 到纯文本一键提取

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)]()

## 🌟 简介

**VibeOCR** 是一个由 AI 驱动的端到端书籍光学字符识别（OCR）工具。它可以将扫描版 PDF 或图片中的文字提取为干净的纯文本。支持涵盖各种主流云端大模型（包括 MinerU、PaddleOCR-VL、PP-OCRv6、Kimi、DeepSeek-OCR、GPT-4o、Claude 等）乃至本地私有化部署（LM Studio / vLLM 等 OpenAI 兼容推理后端）的多种模型，可按精度与成本灵活切换；本地推理数据不出本机、无需云端 API Key。

### 核心特性

- 🔄 **多模型支持** — 支持多种模型/API，根据精度和成本灵活切换
- 🖥️ **本地大模型部署** — 支持私有化部署的推理后端，包括 LM Studio（OpenAI 兼容本地服务）与 vLLM（自托管 OpenAI 兼容服务），数据不出本机、无需云端 API Key
- 📄 **PDF 直传** — 异步模式支持整个 PDF 直接上传（PaddleOCR-VL / PP-OCRv6 / MinerU），无需预先转图片
- 🧹 **智能后处理** — 自动清理 OCR 标签、合并断行段落、转换标点为中文全角
- 📝 **EPUB 元数据 + 版权页提取** — 从版权页自动识别并提取书名、作者、出版信息，生成 meta.yaml 与 COPYRIGHT.md
- 🧰 **多种独立工具** — 拆分、预处理、元数据提取等模块均可单独调用，不依赖完整管线
- 📦 **批处理** — 支持目录级别批量处理 PDF / JPG / PNG 等常见格式
- 💰 **成本可控** — 从免费/低成本的 DeepSeek-OCR 到高精度的 MinerU，满足不同预算

## 🚀 快速开始

### 环境准备

```bash
# 1. 克隆项目
git clone https://github.com/k6G52m4Dz75W/VibeOCR.git
cd VibeOCR

# 2. 安装依赖
pip install -r requirements.txt

# 3. （可选）创建 .gitignore 以保护配置
# 3. （可选）参考 config-sample.py 了解各平台 API Key 变量名
```

### 配置 API Key

推荐通过**环境变量**配置，避免密钥泄露：

```bash
# Linux / macOS
export NVIDIA_API_KEY="nvapi-your-key-here"
export SILICONFLOW_API_KEY="sk-your-key-here"
export MINERU_API_KEY="your-mineru-key-here"

# Windows PowerShell
$env:NVIDIA_API_KEY="nvapi-your-key-here"
$env:SILICONFLOW_API_KEY="sk-your-key-here"
```

### 使用示例

```bash
# 检查版本
python VibeOCR.py --version

# 查看帮助
python VibeOCR.py --help

# 列出所有可用模型
python VibeOCR.py --list-models

# 使用默认模型（DeepSeek-OCR）处理 PDF
python VibeOCR.py document.pdf

# 使用指定模型
python VibeOCR.py document.pdf --model nvidia_kimi-k2.6
python VibeOCR.py document.pdf --model mineru_precision
python VibeOCR.py document.pdf --model paddleocr-vl-1.6

# 跳过指定后处理模块（默认启用去重，可用 -s 或 --skip 禁用）
python VibeOCR.py document.pdf --skip dedup
python VibeOCR.py document.pdf --skip dedup,fullwidth_punct

# 加载外部模型配置（热插拔）
python VibeOCR.py document.pdf --model my_custom --config my_vendor.toml

# 交互式帮助
python VibeOCR.py --help
python utils_clean_text.py -h
python utils_extract_meta.py -h

# 批量处理目录下的所有 PDF/图片
batch_ocr.bat D:\Documents --model mineru_precision

# 独立后处理（对已有 OCR 结果进行清洗，可选 -s/--skip）
python utils_clean_text.py input.txt output.txt
python utils_clean_text.py input.txt output.txt -s dedup

# EPUB 元数据 + 版权页提取（从版权页自动提取）
python utils_extract_meta.py book.pdf                          # 输出到 PDF 同目录
python utils_extract_meta.py book.pdf --model nvidia_kimi-k2.6 -o ./output  # 指定输出目录
python utils_extract_meta.py book.pdf --dry-run --debug        # 预览 + 调试

# 查看独立工具版本
python utils_clean_text.py --version
python utils_insert_pagebreak.py -v
python utils_map_p_br.py --version
python utils_extract_meta.py -v
```

## 🎯 模型选择指南

| 模型 | 成本 | 精度 |
|-------------|------|------|
| <img src="https://www.google.com/s2/favicons?domain=siliconflow.cn&sz=32" width="16" alt="SiliconFlow"> `siliconflow_deepseek-ocr` | 💰 | ⚠️ |
| <img src="https://www.google.com/s2/favicons?domain=siliconflow.cn&sz=32" width="16" alt="SiliconFlow"> `siliconflow_paddleocr-vl-1.5` | 💰 | ⚠️ |
| <img src="https://www.google.com/s2/favicons?domain=mineru.net&sz=32" width="16" alt="MinerU"> `mineru_precision` | 💰 | ⭐⭐⭐⭐⭐ |
| <img src="https://www.google.com/s2/favicons?domain=paddleocr.ai&sz=32" width="16" alt="PaddleOCR"> `paddleocr-vl-1.6` | 💰 | ⭐⭐⭐⭐ |
| <img src="https://www.google.com/s2/favicons?domain=paddleocr.ai&sz=32" width="16" alt="PaddleOCR"> `pp-ocrv6` | 💰 | ⭐⭐⭐ |
| <img src="https://www.google.com/s2/favicons?domain=nvidia.com&sz=32" width="16" alt="NVIDIA NIM"> `nvidia_kimi-k2.6` | 💰 | ⭐⭐⭐⭐⭐ |
| <img src="https://www.google.com/s2/favicons?domain=nvidia.com&sz=32" width="16" alt="NVIDIA NIM"> `nvidia_minimax-m3` | 💰 | ⭐⭐ |
| <img src="https://www.google.com/s2/favicons?domain=nvidia.com&sz=32" width="16" alt="NVIDIA NIM"> `nvidia_step-3.7-flash` | 💰 | ⭐⭐⭐ |
| <img src="https://www.google.com/s2/favicons?domain=nvidia.com&sz=32" width="16" alt="NVIDIA NIM"> `nvidia_nemotron-3-nano` | 💰 | ⭐⭐⭐⭐ |
| <img src="https://www.google.com/s2/favicons?domain=kimi.com&sz=32" width="16" alt="Moonshot AI"> `kimi-k2.6` | 💰💰💰💰 | ⭐⭐⭐⭐⭐ |
| <img src="https://www.google.com/s2/favicons?domain=kimi.com&sz=32" width="16" alt="Moonshot AI"> `kimi-k3` | 💰💰💰💰💰 | ⭐⭐⭐⭐⭐ |
| <img src="https://www.google.com/s2/favicons?domain=openai.com&sz=32" width="16" alt="OpenAI"> `gpt-4o` | 💰💰💰💰💰 | ⭐⭐⭐⭐ |
| <img src="https://www.google.com/s2/favicons?domain=anthropic.com&sz=32" width="16" alt="Anthropic"> `claude-sonnet-5` | 💰💰💰💰💰 | — |
| <img src="https://www.google.com/s2/favicons?domain=lmstudio.ai&sz=32" width="16" alt="LM Studio"> `lmstudio` | 💰💰 | ⭐⭐⭐ |
| <img src="https://www.google.com/s2/favicons?domain=deepseek.com&sz=32" width="16" alt="DeepSeek"> `vllm_deepseek-ocr` | 💰💰💰 | ⭐⭐⭐ |

> 💡 `claude-sonnet-5` 精度尚未实测，留待后续验证。

> 💡 **新手上路推荐**: `mineru_precision` （默认模型）

> ⚠️ **SiliconFlow 托管模型（`siliconflow_deepseek-ocr` / `siliconflow_paddleocr-vl-1.5`）结果可能不稳定**：实测运行中会随机混入无关文本或乱码（如试卷题目列表），而从官方 API（百度 aistudio / 官方 DeepSeek-OCR）跑同一输入完全正常。推断为 SiliconFlow 上第三方上传的权重副本退化或多租户串扰所致，与本项目代码无关。仅建议作为低成本备选，**勿用于生产 OCR 主线**；稳定精度请走 `mineru_precision` 或 `paddleocr-vl-1.6`/`pp-ocrv6`。

## 🖥️ 模型本地部署指南

想用本地私有化部署的模型（数据不出本机、无需云端 API Key）？下面列出已验证的本地部署方案。

### ⚡ vLLM

- 🔗 **DeepSeek-OCR** — 本地 vLLM 部署教程（Windows WSL）：[DeepSeek-OCR 本地安装与部署指南](https://github.com/k6G52m4Dz75W/VisualFrontier/blob/main/DeepSeek-OCR/DeepSeek-OCR_Local_Installation_and_Deployment_Guide_for_Windows_WSL.md)

> 🚀 **视界先锋（VisualFrontier）**：我的另一个项目，专注于本地大模型与多模态应用的部署实践。欢迎 Star / 关注 👉 [github.com/k6G52m4Dz75W/VisualFrontier](https://github.com/k6G52m4Dz75W/VisualFrontier)

## 📁 输出文件说明

处理 `book.pdf` 并使用 `nvidia_kimi-k2.6` 模型时，输出：

```
book_nvidia_kimi-k2.6_raw.txt    ← 原始 API 返回（按批次分割）
book_nvidia_kimi-k2.6.txt        ← 后处理后的最终结果（推荐使用）
book_nvidia_kimi-k2.6.json       ← 异步模型的结构化 JSON 数据
```

## 🧩 项目结构

```
VibeOCR/
├── version.py                 # 版本信息（VERSION, version_info()）
├── VibeOCR.py                 # 主程序 — OCR 核心逻辑
├── config-sample.py           # API Key 配置参考模板（无实际密钥，附申请链接）
├── .gitignore                 # Git 忽略规则
├── requirements.txt           # Python 依赖清单（pip install -r requirements.txt）
├── models_config.py           # 模型配置加载器（从 TOML 读取）
├── models_config.toml         # 模型配置（TOML，15 个内置模型，支持热插拔）
├── postprocess.py             # 后处理流水线入口
├── module_cleaning.py         # 文本清理（标签/空行/空白）
├── module_punctuation.py      # 英文标点 → 中文全角
├── module_heuristic_merge.py  # 断行段落合并
├── module_deduplication.py    # 基于指纹的跨批次去重（独立工具）
├── utils_clean_text.py        # 独立文本清理 CLI
├── utils_map_p_br.py          # OCR 段落空白映射工具
├── utils_insert_pagebreak.py  # EPUB 标准分页符嵌入工具
├── batch_ocr.bat              # Windows 批处理脚本（支持顶部指定 PYTHON_EXE / MODEL / SOURCE）
├── batch_ocr_notes.txt        # 批处理脚本使用说明（Python 路径、默认模型、拖放/双击用法）
├── README.md                  # 项目介绍
├── SPEC.md                    # 项目开发规划书
└── LICENSE                    # MIT 许可证
```

## 🔧 高级用法

### 自定义 Prompt

提示词已经抽离到文件顶部的 `[prompts]` 通用库，避免每个模型重复粘贴。每个模型通过 `prompt_ref` 引用其中一条即可：

```toml
# 文件顶部 [prompts] 段定义命名提示词（只需写一次）
[prompts]
default = """
这是一部小说的扫描文件，请提取正文。
要求：保持段落结构，合并跨页段落，删除页码水印...
"""

[models.nvidia_step]
# ... 其他配置 ...
prompt_ref = "default"   # 引用 [prompts] 中的命名提示词（推荐）
```

- `prompt_ref = "default"` → 引用 `[prompts]` 中的命名提示词
- `prompt_ref = ""` → 显式置空（异步任务模型，如 PaddleOCR / MinerU，无需 prompt）
- 也可直接写内联 `prompt = """..."""` 做一次性覆盖（旧格式仍兼容）
- 模型未指定 `prompt_ref` 时，回退到 `[defaults]` 中的 `default_prompt`（当前为 `default`）

### Docker / 无头服务器

```bash
# 设置环境变量后运行
export OCR_MODEL=mineru_precision
python VibeOCR.py /path/to/book.pdf
```

## 🛡️ 安全提醒

> **⚠️ 重要: 保护你的 API Key**

1. 始终通过**环境变量**配置 API Key（推荐方式），**不要**创建或填写 `config.py`
2. `config-sample.py` 仅作为变量名参考模板，不包含任何真实密钥
3. 如需使用配置文件方式，请将 `config-sample.py` **复制为 `config.py`** 再填写密钥，并确保 `config.py` 已被 `.gitignore` 排除
4. 定期轮换 API Key

## 📊 当前状态

| 状态 | 内容 |
|------|------|
| ✅ 可用 | 核心 OCR 功能、15 种模型（TOML 配置热插拔，提示词抽离到 `[prompts]`，支持本地免鉴权模型）、批处理、后处理、EPUB 元数据 + 版权页提取 |

## 📝 更新日志

### v4.6.0 (2026-07-24) — "Character is like a tree and reputation like a shadow. The shadow is what we think of it; the tree is the real thing."
- **本地大模型支持（vLLM）**: 新增 `vllm_deepseek-ocr`（本地 OpenAI 兼容、免鉴权、input_mode=image，含 vllm_xargs / skip_special_tokens / stream 透传）
- **SDK 路由修复**: `call_llm` / `ocr_batch` 的 OpenAI SDK 路径资格判定去除 `api_key` 依赖，本地无 key 的 OpenAI 兼容服务（如 vLLM）也能正确走 SDK（经 extra_body 透传 vllm_xargs 等），新增回归测试（pytest 101 passed）
- **SiliconFlow 托管模型标注**: `siliconflow_deepseek-ocr` 与 `siliconflow_paddleocr-vl-1.5` 在模型选择指南加 ⚠️ 不稳定标记与注意事项段（结果可能受干扰、偶发无关文本，根因在第三方托管副本而非本项目代码），并统一推荐改用内置 `mineru_precision` / `paddleocr-vl-1.6` / `pp-ocrv6`
- **pp-ocrv6 解析 bug 修复**: 原代码误读 `ocrResults[].text`（字段不存在）导致提取为空，改为正确读取 `ocrResults[].prunedResult.rec_texts`（已对照 PaddleOCR 官方文档确认）
- **模型精度校准**: `mineru_precision` 升 5 星、`nvidia_nemotron-3-nano` 升 4 星、`nvidia_minimax-m3` 实测 batch 降至 3 且精度定为 2 星
- **文档强化**: 简介合并为「云端大模型 + 本地私有化部署（LM Studio / vLLM）」一体化表述；核心特性新增本地部署、EPUB 元数据 + 版权页提取、多种独立工具等卖点；模型表格补入 `vllm_deepseek-ocr`（共 15 种模型）

### v4.5.0 (2026-07-19) — "All action results from thought, so it is thoughts that matter."
- **批处理脚本升级（batch_ocr.bat，功能更新）**:
  - 顶部新增三行可改配置：`PYTHON_EXE`（指定 Python 解释器路径，兼容 Miniconda / 虚拟环境等未注册为默认 python 的情况，真正实现拖放运行）、`MODEL`（默认模型）、`SOURCE`（默认输入源）
  - 新增 `SOURCE` 默认输入源：不拖放、直接双击脚本时，用 `SOURCE` 作为批量处理来源，无需手动拖拽
  - 输入源同时支持「文件夹」（遍历其中所有 pdf/jpg/jpeg/png/bmp/tiff/webp）与「单个文件」两种形态
  - 原 `TARGET_DIR`（拼写错误且语义为「来源」）重命名为 `SOURCE`/`INPUT`，明确其作为输入来源的含义
  - 修复循环内进度计数 bug：原 `%CURRENT%`/`%FILE_COUNT%` 为解析期取值、永远显示初始值，改用延迟展开 `!CURRENT!`/`!FILE_COUNT!`，进度 `[3/7]` 现在正确递增
  - 遵循项目 .bat 零注释铁律：脚本内注释全部移入独立的 `batch_ocr_notes.txt` 使用说明文件，README 项目结构树同步补录该说明文件

### v4.4.2 (2026-07-19) — "Discipline is the bridge between goals and accomplishment."
- **加固 LLM 调用路径（llm_ocr.py）**:
  - OpenAI SDK 路径新增 `_split_sdk_params` 拆参：白名单内正式参数（model/messages/stream/max_tokens/temperature/top_p/seed 等）走 kwargs，扩展字段（如 NIM 的 `reasoning_budget`）经 `extra_body` 完整透传 —— 修复 nemotron 等推理模型走 SDK 时 `reasoning_budget` 被静默丢弃（#20）
  - `call_llm` 与 `ocr_batch` 两条 SDK 路径均修复
- **Anthropic 流式解析分支（#18）**: `ocr_batch` 的 requests 流式循环新增 `fmt == "anthropic"` 分支，按 `content_block_delta` + `delta.text` 解析 —— 消除「给 claude 开 `stream=true` 时 requests 路径解析失败拿空文本」的潜伏 bug
- **流式实时进度（#19）**: 流式收文本时每 chunk 刷新 `已接收 N 字符` 单行进度（\r 覆盖），不再只在最后打印总数
- **models_config.toml 清理（#17）**: 全部流式模型 `Accept` 头对齐为 `text/event-stream`、非流式保持 `application/json`；移除历史残留的 `chat_template_kwargs` 杂质 key

### v4.4.1 (2026-07-19) — "One fails forward toward success."
- **meta 提示词抽离到配置**: 将 `utils_extract_meta.py` 中写死的版权页/元数据提取提示词移入 `models_config.toml` 的 `[meta]` 段（`prompt` 字段），脚本改从配置读取（`META.get("prompt")`），便于在不改代码的情况下调整提取模板
- `models_config.py` 两遍加载新增 `[meta]` 段收集，供元数据提取复用

### v4.4.0 (2026-07-19) — "Peace cannot be kept by force. It can only be achieved by understanding."
- **新增 SiliconFlow PaddleOCR-VL-1.5 模型**: 走 SiliconFlow 同步/流式端点（`model_id = "PaddlePaddle/PaddleOCR-VL-1.5"`），`prompt = ""` 与异步兄弟 `paddleocr-vl-1.6` 对齐（纯图像输入，原生 OCR 模型不需提示词）
- **模型命名体系收敛（关键重构）**:
  - `[models.paddleocr_v6]` → `[models."pp-ocrv6"]`，`content_format` 内部标识 `paddleocr_v6` 统一为 `pp-ocrv6`（VibeOCR.py 5 处 + 测试 + 文档同步）
  - `openai_gpt4o` → `gpt-4o`、`anthropic_claude` → `claude-sonnet-5`：自产自托管省略公司名，段名 key 用 `model_id` 真名
  - `nvidia_nemotron` → `nvidia_nemotron-3-nano`：保留 `nvidia_` 前缀作「托管在 NIM 云」标记，与 step / minimax / kimi 同族一致
  - `utils_map_p_br.py` 格式串 `paddleocr_vl` → `paddleocr-vl-1.6`
- **NVIDIA NIM 各段官方文档审计与对齐**:
  - `nvidia_nemotron-3-nano`: 删除误粘的 `chat_template_kwargs = { enable_thinking = false }`（与 `reasoning_budget` 矛盾且非本模型参数）；`temperature` 0.1 → 0.6（对齐官方 Thinking mode）
  - `nvidia_step-3.7-flash`: `temperature` 0.1 → 1.00（对齐 Build 页官方示例）
  - `nvidia_minimax-m3`: 去掉段名冗余引号；删除 `chat_template_kwargs = { "thinking_mode": "disabled" }` 恢复默认开思考（推理模型开思考更准确）
  - `nvidia_kimi-k2.6`: 补充 `seed = 0`（对齐官方示例，固定随机种子使输出可复现）
  - `nvidia_qwen3.5` 已下架删除
- **文档死引用修复**: README / SPEC / `utils_extract_meta.py` 中旧别名 `nvidia_kimi` → `nvidia_kimi-k2.6`（共 17 处），避免按文档运行找不到段
- **MinerU 上传参数修正**: `is_ocr` 由顶层字段移入 `files[].is_ocr`，贴合 MinerU API 实际结构

### v4.3.1 (2026-07-17) — "A really great talent finds its happiness in execution."
- **修复 本地免鉴权崩溃**: v4.3.0 虽声称 `lmstudio` 免 key 可运行，但空 `api_key` 仍会构造 `OpenAI(api_key="")` 触发 SDK 的 `Missing credentials` 异常。现改为**空 key 时强制走 `requests` 路径**（该路径用 `build_headers`，空 key 本就不发 `Authorization` 头），LM Studio 本地服务免鉴权真正可用
- **补录历史发布格言**: 将 GitHub Releases 标题上已有的 4 句版本格言补入 README 对应更新日志小标题（v4.0 / v4.1 / v4.2 / v4.2.1），使文档与 Release 标题一致；后续发布将由自动化流程统一抽取并写入

### v4.3.0 (2026-07-17) — "The superior man is modest in his speech but exceeds in his actions."
- **提示词去重**: 抽离 `[prompts]` 通用提示词库到文件最前，各模型用 `prompt_ref` 引用；异步 OCR 模型（`paddleocr-vl-1.6`/`pp-ocrv6`/`mineru_precision`）用 `prompt_ref = ""` 显式置空
- **本地免鉴权模型**: 新增 `api_key_env = "none"` 约定（"none"/"no"/空 均视为免 key），`lmstudio` 等本地模型可无需 API Key 直接运行；`build_headers` 在无 key 时不发送 `Authorization` 头
- **修复 TOML 点号 key bug**: `nvidia_kimi-k2.6`/`nvidia_glm-5.2`/`kimi-k2.6` 三个未加引号的点号 model key 此前被 TOML 错误解析为嵌套子表（模型名损坏），已统一改为带引号写法
- `models_config.py` 改为两遍加载（先收集 `[prompts]`/`[defaults]`，再解析 `[models.*]`），外部 `--config` 可自带 `[prompts]` 合并/覆盖
- **优化 `utils_extract_meta.py` 提示词**: `COPYRIGHT.md` 的"出版信息"排版由「表格表头」改为「表格前的 `# 出版信息` 一级标题」（表头留空），输出格式更规范

### v4.2.1 (2026-06-23) — "It is better to be hated for what you are than to be loved for what you are not."
- **ISBN 正式兼容 Pandoc**: 优化 `utils_extract_meta.py` 提示词中 `identifier` 字段，采用 `urn:isbn:` 前缀格式，确保 Pandoc 转 EPUB 时正确识别 ISBN 书号

### v4.2 (2026-06-22) — "Stop worrying about growing old. And think about growing up."
- **一次请求两项产出**: `utils_extract_meta.py` 单次 LLM 调用同时提取 `meta.yaml` + `COPYRIGHT.md`，利用 `---...---` 分隔符拆分
- `--output` 改为指定输出文件夹，固定生成 `meta.yaml` 和 `COPYRIGHT.md` 两个文件
- **`--list-models` 崩溃修复**: `DEFAULT_MODEL` / `CONFIGS` 在重构后未正确导入导致 `NameError`，已补全 import

### v4.1 (2026-06-20) — "Those who don't believe in magic will never find it."
- **YAML 处理重构**: 弃用自建 YAML 解析器，LLM 直接输出 raw YAML，解决 ISBN/编辑团队/印张等字段丢失问题
- 简化 prompt，提升元数据提取完整度

### v4.0 (2026-06-20) — "I can't go back to yesterday because I was a different person then."
- **架构重构**: 抽取 `llm_ocr.py` 公共模块，`VibeOCR.py` 和 `utils_extract_meta.py` 共享同一套 LLM 调用代码
- 删除约 200 行重复代码

### 关键 Bug 修复
| ✅ 已修复 | TOML 配置分离 + 热插拔, 66 个单元测试, 引入 dedup+skip 机制, 删除 config.py 改用环境变量, 全函数类型注解, 移除模块级全局变量, main() 拆分子函数, .gitignore / requirements.txt, 删 deprecated/, 移除 key 格式校验, PaddleOCR Content-Type, 异步结果公共函数, mineru 临时文件, print 统一 f-string, 清空行 |
| 🔧 待改进 | 见 [SPEC.md](SPEC.md) 第 4 节「代码审查报告」 |
| 📋 路线图 | 见 [SPEC.md](SPEC.md) 第 5 节「开发路线图」 |

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！在提交 PR 前请确保：

1. 阅读 [SPEC.md](SPEC.md) 了解项目设计方向
2. 代码风格与现有项目保持一致
3. 添加必要的单元测试（如果有）

## 📄 许可证

[MIT License](LICENSE) © 2026 k6G52m4Dz75W

---

<p align="center">
  <sub>用 ❤️ 和 AI 构建 · 为书籍数字化而生</sub>
</p>

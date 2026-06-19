# VibeOCR 📖✨

> **智能端到端书籍 OCR 解决方案** — 多模型 AI 驱动，PDF 到纯文本一键提取

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)]()

## 🌟 简介

**VibeOCR** 是一个由 AI 驱动的端到端书籍光学字符识别（OCR）工具。它支持多种主流 AI 模型（包括 DeepSeek-OCR、GPT-4o、Claude、Kimi、PaddleOCR-VL、MinerU 等），可以将扫描版 PDF 或图片中的文字提取为干净的纯文本。

### 核心特性

- 🔄 **多模型支持** — 支持 10+ 种模型/API，根据精度、成本和速度灵活切换
- 📄 **PDF 直传** — 异步模式支持整个 PDF 直接上传（PaddleOCR-VL / MinerU），无需预先转图片
- 🧹 **智能后处理** — 自动清理 OCR 标签、合并断行段落、转换标点为中文全角
- 📦 **批处理** — 支持目录级别批量处理 PDF / JPG / PNG 等常见格式
- 💰 **成本可控** — 从免费/低成本的 DeepSeek-OCR 到高精度的 MinerU，满足不同预算

## 🚀 快速开始

### 环境准备

```bash
# 1. 克隆项目
git clone https://github.com/your-username/VibeOCR.git
cd VibeOCR

# 2. 安装依赖
pip install -r requirements.txt

# 3. （可选）创建 .gitignore 以保护配置
#    项目已自带 .gitignore，确认 config.py 已被排除
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
# 使用默认模型（DeepSeek-OCR）处理 PDF
python VibeOCR3.py document.pdf

# 使用指定模型
python VibeOCR3.py document.pdf --model nvidia_kimi
python VibeOCR3.py document.pdf --model mineru_precision
python VibeOCR3.py document.pdf --model paddleocr_vl

# 批量处理目录下的所有 PDF/图片
batch_ocr.bat D:\Documents --model mineru_precision

# 独立后处理（对已有 OCR 结果进行清洗）
python clean_text.py input.txt output.txt
```

## 🎯 模型选择指南

| 模型配置 Key | 适用场景 | 成本 | 精度 | 速度 |
|-------------|---------|------|------|------|
| `siliconflow_deepseek-ocr` | 普通书籍、小说 | 💰低 | ⭐⭐⭐ | ⚡快 |
| `mineru_precision` | 高精度扫描件、复杂版式 | 💰中 | ⭐⭐⭐⭐⭐ | 🐢慢（异步） |
| `paddleocr_vl` | 中文文档、古籍 | 💰低 | ⭐⭐⭐⭐ | 🐢慢（异步） |
| `nvidia_kimi` | 中英文书籍、高通量 | 💰中 | ⭐⭐⭐⭐ | ⚡⚡快 |
| `moonshot_kimi` | 中文长文档 | 💰中 | ⭐⭐⭐⭐ | ⚡快 |
| `nvidia_nemotron` | 超大上下文需求 | 💰中 | ⭐⭐⭐ | ⚡⚡快 |
| `openai_gpt4o` | 英文为主、稳定性优先 | 💰高 | ⭐⭐⭐⭐⭐ | ⚡快 |
| `anthropic_claude` | 多语言、推理任务 | 💰高 | ⭐⭐⭐⭐⭐ | ⚡快 |

> 💡 **新手上路推荐**: 从 `siliconflow_deepseek-ocr` 开始（免费额度/低成本），遇到复杂版式时切换到 `mineru_precision`

## 📁 输出文件说明

处理 `book.pdf` 并使用 `nvidia_kimi` 模型时，输出：

```
book_nvidia_kimi_raw.txt    ← 原始 API 返回（按批次分割）
book_nvidia_kimi.txt        ← 后处理后的最终结果（推荐使用）
book_nvidia_kimi.json       ← 异步模型的结构化 JSON 数据
```

## 🧩 项目结构

```
VibeOCR/
├── VibeOCR3.py           # 主程序 — OCR 核心逻辑
├── config.py             # API Key 配置（勿提交到 git!）
├── .gitignore            # Git 忽略规则（排除 config.py 等敏感文件）
├── requirements.txt      # Python 依赖清单（pip install -r requirements.txt）
├── models_config.py      # 模型配置字典（10+ 模型）
├── postprocess.py        # 后处理流水线入口
├── cleaning.py           # 文本清理（标签/空行/空白）
├── punctuation.py        # 英文标点 → 中文全角
├── heuristic_merge.py    # 断行段落合并
├── deduplication.py      # 基于指纹的跨批次去重（独立工具）
├── clean_text.py         # 独立文本清理 CLI
├── map_br8.py            # OCR 段落空白映射工具
├── insert_page_div.py    # 分页 <div> 标签嵌入工具
├── add_br_to_ocr.py      # 基于几何间距的段落检测
├── batch_ocr.bat         # Windows 批处理脚本
├── README.md             # 项目介绍
├── SPEC.md               # 项目开发规划书
├── LICENSE               # MIT 许可证
└── deprecated/           # 历史版本归档
    └── paragraphbreak.py # （已弃用）段落分割
```

## 🔧 高级用法

### 自定义 Prompt

在 `models_config.py` 中修改对应模型的 `prompt` 字段即可：

```python
"nvidia_kimi": {
    ...
    "prompt": """请逐字提取图片中的文本，严禁改写...
要求：
1. 逐字转录，保持原文每一个字、每一个标点不变
2. 保持段落结构，合并被分页打断的段落
3. 删除页脚页码和水印图案"""
}
```

### Docker / 无头服务器

```bash
# 设置环境变量后运行
export OCR_MODEL=mineru_precision
python VibeOCR3.py /path/to/book.pdf
```

## 🛡️ 安全提醒

> **⚠️ 重要: 保护你的 API Key**

1. 优先使用**环境变量**配置 API Key，而非直接修改 `config.py`
2. 项目已自带 `.gitignore`，`config.py` 已被排除 —— 在添加真实密钥前确保这一点
3. 定期轮换 API Key

## 📊 当前状态

| 状态 | 内容 |
|------|------|
| ✅ 可用 | 核心 OCR 功能、10 种模型、批处理、后处理 |
| ✅ 已修复 | 添加 .gitignore / requirements.txt, 清理 postprocess.py 空行, paragraphbreak.py 移入 deprecated |
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

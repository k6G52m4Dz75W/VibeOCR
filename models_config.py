# models_config.py
# 模型配置文件 - 支持多供应商API

CONFIGS = {
    "nvidia_kimi": {
        "name": "NVIDIA NIM / Kimi K2.6",
        "api_url": "https://integrate.api.nvidia.com/v1/chat/completions",
        "model_id": "moonshotai/kimi-k2.6",
        "api_key_env": "NVIDIA_API_KEY",
        "batch_size": 5,
        "headers": {
            "Accept": "application/json"
        },
        "payload_template": {
            "max_tokens": 16384,
            "temperature": 0.1,
            "top_p": 1.00,
            "stream": False,
            "chat_template_kwargs": {"thinking": False}
        },
        "timeout": 180,
        "content_format": "openai",
        "prompt": """请逐字提取图片中的文本，严禁改写、替换同义词或调整语序。
要求：
1. 逐字转录，保持原文每一个字、每一个标点不变
2. 禁止将"为何"改为"为什么"，禁止将"一定能"改为"一定能够"等任何同义替换
3. 保持段落结构，识别跨页段落，合并被分页打断的段落
4. 删除页脚中的页码和风眼文字和图样，以及右下方的请开通会员和XX扫描王的水印图案
5. 使用规范的中文全角标点符号
6. 严格忠实于原文，不增加、遗漏、修改任何文字"""
    },

    "nvidia_step": {
        "name": "NVIDIA NIM / step-3.7-flash",
        "api_url": "https://integrate.api.nvidia.com/v1/chat/completions",
        "model_id": "stepfun-ai/step-3.7-flash",
        "api_key_env": "NVIDIA_API_KEY",
        "batch_size": 5,
        "headers": {
            "Accept": "application/json"
        },
        "payload_template": {
            "max_tokens": 16384,
            "temperature": 0.1,
            "top_p": 0.95,
            "stream": True,
        },
        "timeout": 180,
        "content_format": "openai",
        "prompt": """这是一部小说的扫描文件，请提取正文。
要求：
1. 保持段落结构，识别跨页段落，合并被分页打断的段落
2. 删除页脚中的页码和风眼文字和图样，以及右下方的请开通会员和XX扫描王的水印图案。
3. 请直接输出纯文本，严格忠实于原文，不增加，遗漏，修改原文文本。
4. 使用规范的中文全角标点符号。"""
    },

    "nvidia_nemotron": {
        "name": "NVIDIA NIM / nemotron-3-nano-omni-30b-a3b-reasoning",
        "api_url": "https://integrate.api.nvidia.com/v1/chat/completions",
        "model_id": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
        "api_key_env": "NVIDIA_API_KEY",
        "batch_size": 5,
        "headers": {
            "Accept": "application/json"
        },
        "payload_template": {
            "max_tokens": 65536,
            "temperature": 0.1,
            "top_p": 0.95,
            "stream": True,
            "chat_template_kwargs":{"enable_thinking":False},"reasoning_budget":16384
        },
        "timeout": 180,
        "content_format": "openai",
        "prompt": """这是一部小说的扫描文件，请提取正文。
要求：
1. 保持段落结构，识别跨页段落，合并被分页打断的段落
2. 删除页脚中的页码和风眼文字和图样，以及右下方的请开通会员和XX扫描王的水印图案。
3. 请直接输出纯文本，严格忠实于原文，不增加，遗漏，修改原文文本。
4. 使用规范的中文全角标点符号。"""
    },

    "nvidia_qwen3.5": {
        "name": "NVIDIA NIM / qwen3.5-397b-a17b",
        "api_url": "https://integrate.api.nvidia.com/v1/chat/completions",
        "model_id": "qwen/qwen3.5-397b-a17b",
        "api_key_env": "NVIDIA_API_KEY",
        "batch_size": 5,
        "headers": {
            "Accept": "application/json"
        },
        "payload_template": {
            "max_tokens": 16384,
            "temperature": 0.6,
            "top_p": 0.95,
            "stream": True,
            "chat_template_kwargs":{"enable_thinking":False}
        },
        "timeout": 180,
        "content_format": "openai",
        "prompt": """这是一部小说的扫描文件，请提取正文。
要求：
1. 保持段落结构，识别跨页段落，合并被分页打断的段落
2. 删除页脚中的页码和风眼文字和图样，以及右下方的请开通会员和XX扫描王的水印图案。
3. 请直接输出纯文本，严格忠实于原文，不增加，遗漏，修改原文文本。
4. 使用规范的中文全角标点符号。"""
    },

    "siliconflow_deepseek-ocr": {
        "name": "SiliconFlow / DeepSeek-OCR",
        "api_url": "https://api.siliconflow.cn/v1/chat/completions",
        "model_id": "deepseek-ai/DeepSeek-OCR",
        "api_key_env": "SILICONFLOW_API_KEY",
        "batch_size": 1,  # DeepSeek-OCR 只支持1次1张
        "headers": {
            "Accept": "application/json",
            "Content-Type": "application/json"
        },
        "payload_template": {
            "max_tokens": 4096,
            "temperature": 0.2,
            "top_p": 1.00,
            "stream": True
        },
        "timeout": 120,
        "content_format": "openai",
        "note": "总上下文限制8K，max_tokens建议不超过4096",
        "prompt": """<tr>
<|grounding|>Convert the document to markdown."""
    },

    "openai_gpt4o": {
        "name": "OpenAI / GPT-4o",
        "api_url": "https://api.openai.com/v1/chat/completions",
        "model_id": "gpt-4o",
        "api_key_env": "OPENAI_API_KEY",
        "batch_size": 2,
        "headers": {
            "Accept": "application/json"
        },
        "payload_template": {
            "max_tokens": 4096,
            "temperature": 0.2,
            "top_p": 1.00,
            "stream": False
        },
        "timeout": 180,
        "content_format": "openai",
        "prompt": """Extract the main text from this scanned novel page.
Requirements:
1. Maintain paragraph structure, merge paragraphs broken across pages
2. Remove page numbers, watermarks, and advertisements
3. Output plain text only, strictly faithful to the original
4. Use standard Chinese full-width punctuation"""
    },

    "anthropic_claude": {
        "name": "Anthropic / Claude 3.5 Sonnet",
        "api_url": "https://api.anthropic.com/v1/messages",
        "model_id": "claude-3-5-sonnet-20241022",
        "api_key_env": "ANTHROPIC_API_KEY",
        "batch_size": 2,
        "headers": {
            "Accept": "application/json",
            "anthropic-version": "2023-06-01"
        },
        "payload_template": {
            "max_tokens": 4096,
            "temperature": 0.2
        },
        "timeout": 180,
        "content_format": "anthropic",
        "prompt": """请提取这部扫描小说的正文内容。
要求：
1. 保持段落结构，合并被分页打断的段落
2. 删除页脚页码、水印文字和广告图案
3. 直接输出纯文本，忠实原文不做修改
4. 使用中文全角标点符号
5. 如遇模糊文字，结合上下文推断"""
    },

    "moonshot_kimi": {
        "name": "Moonshot AI / Kimi K2.6",
        "api_url": "https://api.moonshot.cn/v1/chat/completions",
        "model_id": "kimi-k2-6",
        "api_key_env": "MOONSHOT_API_KEY",
        "batch_size": 5,
        "headers": {
            "Accept": "application/json"
        },
        "payload_template": {
            "max_tokens": 16384,
            "temperature": 0.2,
            "top_p": 1.00,
            "stream": False
        },
        "timeout": 180,
        "content_format": "openai",
        "prompt": """这是一部小说的扫描文件，请提取正文。
要求：
1. 保持段落结构，识别跨页段落，合并被分页打断的段落
2. 删除页脚中的页码和风眼文字和图样，以及右下方的请开通会员和XX扫描王的水印图案。
3. 请直接输出纯文本，严格忠实于原文，不增加，遗漏，修改原文文本。
4. 使用规范的中文全角标点符号。"""
    },

    "paddleocr_vl": {
        "name": "PaddleOCR-VL-1.6 (AIStudio 异步API)",
        "api_url": "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs",
        "model_id": "PaddleOCR-VL-1.6",
        "api_key_env": "PADDLEOCR_API_KEY",
        "batch_size": 1,  # 异步任务，一次提交整个PDF
        "headers": {
            "Accept": "application/json"
        },
        "payload_template": {
            "useDocOrientationClassify": False,
            "useDocUnwarping": False,
            "useChartRecognition": False,
            "useLayoutDetection": True,
            "prettifyMarkdown": False,
            "visualize": False
        },
        "timeout": 30,
        "content_format": "paddleocr_async",
        "note": "异步任务模式：提交PDF后轮询获取结果，结果返回markdown格式。支持PDF直接上传，无需预先转图片。",
        "prompt": None  # PaddleOCR-VL 不需要 prompt，通过 optionalPayload 控制行为
    },

    "mineru_precision": {
        "name": "MinerU Precision Extract API (v4)",
        "api_url": "https://mineru.net/api/v4",
        "model_id": "vlm",
        "api_key_env": "MINERU_API_KEY",
        "batch_size": 1,
        "headers": {
            "Accept": "application/json",
            "Content-Type": "application/json"
        },
        "payload_template": {
            "model_version": "vlm",
            "is_ocr": True,
            "enable_formula": True,
            "enable_table": True,
            "language": "ch",
            "extra_formats": []
        },
        "timeout": 30,
        "content_format": "mineru_async",
        "note": "MinerU 高精度提取API。支持200MB/200页。流程：申请上传URL -> PUT上传文件 -> 轮询batch结果 -> 下载zip提取full.md。扫描件请务必开启is_ocr。",
        "prompt": None
    },

    "custom": {
        "name": "自定义API",
        "api_url": "https://your-api-endpoint.com/v1/chat/completions",
        "model_id": "your-model-name",
        "api_key_env": "CUSTOM_API_KEY",
        "batch_size": 1,
        "headers": {
            "Accept": "application/json"
        },
        "payload_template": {
            "max_tokens": 4096,
            "temperature": 0.2,
            "top_p": 1.00,
            "stream": False
        },
        "timeout": 180,
        "content_format": "openai",
        "prompt": """请从扫描图片中提取文本内容。
要求：保持原文结构，删除页码水印，使用规范标点。"""
    }
}

# 默认使用的模型配置
DEFAULT_MODEL = "siliconflow_deepseek-ocr"
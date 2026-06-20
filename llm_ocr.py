"""
llm_ocr.py — LLM OCR 公共基础设施。

为 VibeOCR 主程序及附属工具（utils_extract_meta 等）提供统一的
PDF 转图片、模型配置加载、LLM API 调用能力。

用法:
    from llm_ocr import load_model_config, pdf_pages_to_b64, call_llm, ocr_batch
"""

import sys
import os
import time
import json
import base64
from typing import Any

import requests

try:
    import fitz
    from PIL import Image
    from io import BytesIO
except ImportError:
    print("❌ 需要安装: pip install pymupdf pillow")
    sys.exit(1)

try:
    from openai import OpenAI
    OPENAI_AVAILABLE: bool = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    from models_config import CONFIGS, DEFAULT_MODEL
except ImportError:
    print("❌ 请将 models_config.py 放在同一目录下")
    sys.exit(1)

try:
    import config as config_module
except ImportError:
    config_module = None


# ======================================================================
# 模型配置
# ======================================================================

def load_model_config(model_key: str | None = None) -> dict[str, Any]:
    """加载模型配置，支持从参数、环境变量或 config.py 读取"""
    if model_key is None:
        model_key = os.environ.get("OCR_MODEL", DEFAULT_MODEL)

    if model_key not in CONFIGS:
        print(f"❌ 未知模型配置: {model_key}")
        print(f"可用配置: {', '.join(CONFIGS.keys())}")
        print("提示: 使用 VibeOCR.py --list-models 查看完整列表")
        sys.exit(1)

    config = CONFIGS[model_key].copy()
    api_key_env = config["api_key_env"]
    api_key = os.environ.get(api_key_env)

    if not api_key and config_module:
        api_key = getattr(config_module, api_key_env, None)

    if not api_key:
        print(f"⚠️  API Key 未配置")
        print(f"   环境变量: export {api_key_env}=your_key")
        if config_module:
            print(f"   或修改 config.py 中的 {api_key_env}")
        sys.exit(1)

    config["api_key"] = api_key
    config["model_key"] = model_key

    return config


# ======================================================================
# PDF → base64 图片
# ======================================================================

def pdf_pages_to_b64(pdf_path: str, dpi: int = 300, max_width: int = 1600,
                     page_range: str | None = None) -> tuple[list[dict[str, Any]], int]:
    """
    将 PDF 页面转换为 base64 图片列表。

    Args:
        pdf_path: PDF 文件路径
        dpi: 渲染 DPI
        max_width: 图片最大宽度（px）
        page_range: 页码范围，如 "1-3" 或 "1"（None 表示全部）

    Returns:
        (images, total_pages) — images 是 OpenAI 兼容的图片消息列表
    """
    doc = fitz.open(pdf_path)
    total = len(doc)

    # 解析页码范围
    if page_range:
        if "-" in page_range:
            parts = page_range.split("-")
            start = max(0, int(parts[0]) - 1)
            end = min(int(parts[1]), total)
        else:
            start = max(0, int(page_range) - 1)
            end = start + 1
    else:
        start = 0
        end = total

    images = []
    for i in range(start, end):
        page = doc[i]
        pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72))
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        if img.width > max_width:
            ratio = max_width / img.width
            new_height = int(img.height * ratio)
            img = img.resize((max_width, new_height), Image.LANCZOS)

        buf = BytesIO()
        img.save(buf, format="PNG", optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode()

        images.append({
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64," + b64}
        })
        size_kb = len(buf.getvalue()) / 1024
        total_info = f" (共{total}页)" if total > 1 else ""
        print(f"  第{i+1}/{total}页已编码 ({int(size_kb)}KB){total_info}")

    doc.close()
    return images, end - start


def image_file_to_b64(image_path: str, max_width: int = 1600) -> list[dict[str, Any]]:
    """将单张图片文件转换为 base64 图片消息列表"""
    img = Image.open(image_path)
    if img.width > max_width:
        ratio = max_width / img.width
        new_h = int(img.height * ratio)
        img = img.resize((max_width, new_h), Image.LANCZOS)

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return [{
        "type": "image_url",
        "image_url": {"url": f"data:image/png;base64,{b64}"},
    }]


# ======================================================================
# 请求构建
# ======================================================================

def build_payload(config: dict[str, Any], messages: list[dict]) -> dict[str, Any]:
    """根据模型配置构建请求体"""
    model_id = config["model_id"]
    template = config["payload_template"].copy()
    payload = {"model": model_id, "messages": messages, **template}
    return payload


def build_headers(config: dict[str, Any]) -> dict[str, str]:
    """构建请求头"""
    headers = config["headers"].copy()
    headers["Authorization"] = f"Bearer {config['api_key']}"
    return headers


# ======================================================================
# LLM API 调用
# ======================================================================

def call_llm(
    config: dict[str, Any],
    images: list[dict[str, Any]],
    prompt: str,
    max_retries: int = 2,
    retry_delay: int = 3,
    verbose: bool = True,
) -> str:
    """
    通用单次 LLM 调用：发送图片 + prompt，返回文本响应。

    适用于工具类场景（元数据提取、单页 OCR 等）。
    优先使用 openai 库，否则 fallback 到 requests。
    支持 openai 和 anthropic 两种消息格式。

    Args:
        config: 模型配置
        images: base64 图片消息列表
        prompt: 文本提示词
        max_retries: 最大重试次数
        retry_delay: 初始重试延迟（秒），每次翻倍
        verbose: 是否打印详细信息

    Returns:
        LLM 返回的文本内容
    """
    api_url = config["api_url"]
    api_key = config["api_key"]
    fmt = config["content_format"]
    template = config.get("payload_template", {})
    model_id = config["model_id"]

    # 构建消息内容（图片在前，prompt 在后）
    message_content = list(images)
    message_content.append({"type": "text", "text": prompt})

    if fmt == "anthropic":
        messages = [{"role": "user", "content": message_content}]
    else:
        messages = [{"role": "user", "content": message_content}]

    can_use_openai = OPENAI_AVAILABLE and fmt == "openai"

    last_error = None
    for attempt in range(1, max_retries + 1):
        if verbose:
            print(f"  发送请求 (尝试 {attempt}/{max_retries})...", end=" ")
        try:
            if can_use_openai:
                base_url = api_url.replace("/chat/completions", "")
                client = OpenAI(api_key=api_key, base_url=base_url)
                response = client.chat.completions.create(
                    model=model_id,
                    messages=messages,
                    max_tokens=template.get("max_tokens", 4096),
                    temperature=template.get("temperature", 0.1),
                    top_p=template.get("top_p", 1.0),
                )
                text = response.choices[0].message.content
                if verbose:
                    print(f"✅ {len(text)} 字符")
                return text
            else:
                # Anthropic 格式
                if fmt == "anthropic":
                    payload = {"model": model_id, "messages": messages,
                               "max_tokens": template.get("max_tokens", 4096),
                               "temperature": template.get("temperature", 0.1)}
                    headers = {**config.get("headers", {}), "x-api-key": api_key,
                               "anthropic-version": "2023-06-01"}
                    resp = requests.post(api_url, headers=headers, json=payload, timeout=120)
                    resp.raise_for_status()
                    text = resp.json()["content"][0]["text"]
                else:
                    # OpenAI 兼容格式（requests 路径）
                    payload = {"model": model_id, "messages": messages, **template}
                    headers = build_headers(config)
                    resp = requests.post(api_url, headers=headers, json=payload,
                                         timeout=config.get("timeout", 120))
                    resp.raise_for_status()
                    text = resp.json()["choices"][0]["message"]["content"]

                if verbose:
                    print(f"✅ {len(text)} 字符")
                return text

        except Exception as e:
            last_error = e
            if verbose:
                print(f"❌ {e}")
            if attempt < max_retries:
                if verbose:
                    print(f"  ⏳ {retry_delay}秒后重试...")
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                if verbose:
                    print("  💥 已达到最大重试次数，放弃")

    raise last_error


def ocr_batch(config: dict[str, Any], images: list[dict[str, Any]],
              batch_info: str, max_retries: int = 3, retry_delay: int = 5) -> str:
    """
    发送一批图片的 OCR 请求，支持 stream / non-stream 模式。

    这是 VibeOCR 主程序使用的批量 OCR 函数，包含完整的进度输出和重试逻辑。
    """
    prompt = config.get("prompt", "请提取图片中的文本内容。")
    content = [{"type": "text", "text": prompt + "\n\n【当前批次: " + batch_info + "】"}]
    content.extend(images)

    total_size = sum(len(img["image_url"]["url"]) for img in images)
    print(f"  总base64大小: {int(total_size/1024)}KB")

    api_url = config["api_url"]
    fmt = config["content_format"]

    if fmt == "anthropic":
        messages = [{"role": "user", "content": content}]
    else:
        messages = [{"role": "user", "content": content}]

    payload = build_payload(config, messages)
    use_stream = payload.get("stream", False)

    base_url = api_url.replace("/chat/completions", "")
    can_use_openai = OPENAI_AVAILABLE and fmt == "openai"

    last_error = None
    for attempt in range(1, max_retries + 1):
        lib_name = "openai库" if can_use_openai else "requests"
        print(f"  发送请求 [{lib_name}] (尝试 {attempt}/{max_retries}, stream={use_stream})...", end=" ")
        try:
            if can_use_openai:
                client = OpenAI(api_key=config["api_key"], base_url=base_url)
                msg_content = []
                for img in images:
                    msg_content.append(img)
                msg_content.append({"type": "text", "text": prompt + "\n\n【当前批次: " + batch_info + "】"})

                response = client.chat.completions.create(
                    model=config["model_id"],
                    messages=[{"role": "user", "content": msg_content}],
                    stream=use_stream,
                    max_tokens=payload.get("max_tokens", 4096),
                    temperature=payload.get("temperature", 0.2),
                    top_p=payload.get("top_p", 1.0)
                )

                if use_stream:
                    text = ""
                    for chunk in response:
                        if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                            text += chunk.choices[0].delta.content
                else:
                    text = response.choices[0].message.content
                print(f"✅ {len(text)}字符 ({'流式' if use_stream else '非流式'})")
                return text
            else:
                headers = build_headers(config)
                timeout_val = config["timeout"]
                resp = requests.post(api_url, headers=headers, json=payload,
                                     timeout=timeout_val, stream=use_stream)
                resp.raise_for_status()

                if use_stream:
                    text = ""
                    for line in resp.iter_lines():
                        if line:
                            line_str = line.decode("utf-8")
                            if line_str.startswith("data: "):
                                data_str = line_str[6:]
                                if data_str == "[DONE]":
                                    break
                                try:
                                    chunk = json.loads(data_str)
                                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                                    if delta.get("content"):
                                        text += delta["content"]
                                except json.JSONDecodeError:
                                    continue
                else:
                    data = resp.json()
                    text = (data["content"][0]["text"] if fmt == "anthropic"
                            else data["choices"][0]["message"]["content"])
                print(f"✅ {len(text)}字符 ({'流式' if use_stream else '非流式'})")
                return text

        except Exception as e:
            last_error = e
            print(f"❌ 失败: {e}")
            if attempt < max_retries:
                print(f"  ⏳ {retry_delay}秒后重试...")
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                print("  💥 已达到最大重试次数，放弃")

    raise last_error

# -*- coding: utf-8 -*-
"""
utils_extract_meta.py — 从 PDF/图片中提取 EPUB 元数据 (meta.yaml)

利用 VibeOCR 的 LLM OCR 管线，从书籍版权页/封面页提取结构化元数据，
输出标准的 EPUB meta.yaml 格式。

用法:
    python utils_extract_meta.py book.pdf -o meta.yaml
    python utils_extract_meta.py book.pdf --model nvidia_kimi
    python utils_extract_meta.py book.pdf --pages 1-3 --output meta.yaml
    python utils_extract_meta.py book.pdf --dry-run        # 预览不保存
    python utils_extract_meta.py -v
"""

import sys
import os
import json
import re
import argparse

try:
    import version
    VERSION = version.VERSION
except ImportError:
    VERSION = "0.0.0"

# 延迟导入（仅在需要时）
FITZ_AVAILABLE = False
PIL_AVAILABLE = False
OPENAI_AVAILABLE = False

# ---- 内置 prompt ----

META_PROMPT = """你是一名专业的图书元数据提取专家。请仔细分析图片中的文字（特别是版权页、书名页），提取以下元数据信息。

必须以 YAML 格式输出，仅输出 YAML 内容，不要添加任何额外说明：

---
# 基本标识信息
title:                    # 书名（必须）
author:                   # 作者（列表）
publisher:                # 出版社
publisher_address:        # 出版社地址
publisher_url:            # 出版社网址

# 出版信息
date:                     # 出版日期 (YYYY-MM-DD 格式)
edition:                  # 版次说明（如 "2026年1月第1版"）
print_run:                # 印刷次数（如 "2026年1月第1次印刷"）

# ISBN
identifier:
  - scheme: ISBN-13
    value:                # 13位 ISBN 号

# 制作信息
producer:                 # 制作公司/排版公司
pages:                    # 总页数
word_count:               # 字数（如 "250千字"）

# 价格
price:                    # 定价（如 "49.80元"）
price_currency: CNY

# 编辑团队
contributor:              # 列表，每项含 role 和 name
  - role: 责任编辑
    name:
  - role: 特约编辑
    name:
  - role:
    name:

# 语言
language: zh-CN

# 备注
note:                     # 其他需要记录的信息

如果某些信息在图片中无法找到，请留空或使用合适的默认值。
请仔细从图片中提取每个字段，确保 ISBN、出版日期等关键信息准确无误。
"""


# ---- YAML 构建器（无需 PyYAML 依赖） ----

def _yaml_value(value, indent: int = 0) -> str:
    """将 Python 值序列化为 YAML 行"""
    prefix = "  " * indent
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        # 如果需要引号
        if any(ch in value for ch in (':', '#', '{', '}', '[', ']', ',', '&', '*', '?', '|', '-', '<', '>', '=', '!', '%', '@', '`')):
            escaped = value.replace('\\', '\\\\').replace('"', '\\"')
            return f'"{escaped}"'
        return value
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, dict):
                # 列表下的 dict，用 "- key: value" 格式
                lines.append(f"{prefix}-")
                for k, v in item.items():
                    if v is not None and v != "":
                        lines.append(f"{prefix}  {k}: {_yaml_value(v, indent + 1)}")
            else:
                lines.append(f"{prefix}- {_yaml_value(item, indent + 1)}")
        return "\n".join(lines)
    if isinstance(value, dict):
        lines = []
        for k, v in value.items():
            if v is not None and v != "" and not (isinstance(v, list) and len(v) == 0):
                lines.append(f"{prefix}{k}: {_yaml_value(v, indent + 1)}")
        return "\n".join(lines)
    return str(value)


def dict_to_yaml(data: dict) -> str:
    """将 dict 转换为 YAML 字符串"""
    return _yaml_value(data).strip()


# ---- LLM 调用 ----

def _init_libs():
    """延迟加载所需库"""
    global FITZ_AVAILABLE, PIL_AVAILABLE, OPENAI_AVAILABLE

    try:
        import fitz
        FITZ_AVAILABLE = True
    except ImportError:
        FITZ_AVAILABLE = False

    try:
        from PIL import Image
        PIL_AVAILABLE = True
    except ImportError:
        PIL_AVAILABLE = False

    try:
        from openai import OpenAI
        OPENAI_AVAILABLE = True
    except ImportError:
        OPENAI_AVAILABLE = False


def _pdf_to_images(pdf_path: str, pages_spec: str = "1-3",
                   dpi: int = 200, max_width: int = 1600) -> tuple[list[dict], int]:
    """将 PDF 的前几页转为 base64 图片（复用 VibeOCR 逻辑）"""
    import fitz
    from PIL import Image
    from io import BytesIO
    import base64

    # 解析页码范围
    if "-" in pages_spec:
        parts = pages_spec.split("-")
        start = max(0, int(parts[0]) - 1)  # 转为 0-based
        end = int(parts[1])  # 转为 0-based exclusive
    else:
        start = max(0, int(pages_spec) - 1)
        end = start + 1

    doc = fitz.open(pdf_path)
    total = len(doc)
    end = min(end, total)

    images = []
    for i in range(start, end):
        page = doc[i]
        pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72))
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        if img.width > max_width:
            ratio = max_width / img.width
            new_h = int(img.height * ratio)
            img = img.resize((max_width, new_h), Image.LANCZOS)

        buf = BytesIO()
        img.save(buf, format="PNG", optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode()
        images.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{b64}"},
        })
        size_kb = len(buf.getvalue()) / 1024
        print(f"  📄 第{i+1}/{total}页已编码 ({int(size_kb)}KB)")

    doc.close()
    return images, end - start


def _call_llm(config: dict, images: list[dict], prompt: str) -> str:
    """
    调用 LLM 进行元数据提取。

    优先使用 openai 库（兼容格式），否则 fallback 到 requests。
    """
    from openai import OpenAI
    import requests as req

    api_url = config["api_url"]
    api_key = config["api_key"]
    model_id = config["model_id"]
    template = config.get("payload_template", {})
    fmt = config.get("content_format", "openai")

    # 构建消息内容（图片在前，prompt 在后）
    message_content = list(images)
    message_content.append({"type": "text", "text": prompt})

    can_use_openai = OPENAI_AVAILABLE and fmt == "openai"

    if can_use_openai:
        base_url = api_url.replace("/chat/completions", "")
        client = OpenAI(api_key=api_key, base_url=base_url)

        response = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": message_content}],
            max_tokens=template.get("max_tokens", 4096),
            temperature=template.get("temperature", 0.1),
            top_p=template.get("top_p", 1.0),
        )
        return response.choices[0].message.content
    else:
        # Anthropic 格式
        if fmt == "anthropic":
            payload = {
                "model": model_id,
                "messages": [{"role": "user", "content": message_content}],
                "max_tokens": template.get("max_tokens", 4096),
                "temperature": template.get("temperature", 0.1),
            }
            headers = {
                **config.get("headers", {}),
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            }
            resp = req.post(api_url, headers=headers, json=payload, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            return data["content"][0]["text"]
        else:
            # OpenAI 兼容格式（requests 路径）
            payload = {
                "model": model_id,
                "messages": [{"role": "user", "content": message_content}],
                **template,
            }
            headers = {
                **config.get("headers", {}),
                "Authorization": f"Bearer {api_key}",
            }
            resp = req.post(api_url, headers=headers, json=payload, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]


def _parse_yaml_response(text: str) -> dict:
    """从 LLM 的 YAML 输出中提取结构化数据"""
    # 尝试提取 YAML 块（可能在 ```yaml ... ``` 中）
    yaml_block = text
    match = re.search(r"```(?:yaml)?\s*\n(.*?)\n```", text, re.DOTALL)
    if match:
        yaml_block = match.group(1)

    # 去掉开始的 ---
    yaml_block = re.sub(r"^---\s*\n", "", yaml_block.strip())

    # 用简单的行解析提取键值
    result = {}
    current_key = None
    current_list = []
    current_dict = {}
    in_list = False
    in_dict_in_list = False
    list_dict_keys = []

    def _flush_list():
        nonlocal current_list, current_dict, in_list, in_dict_in_list, list_dict_keys
        if in_dict_in_list and current_dict:
            current_list.append(current_dict)
            current_dict = {}
        if in_list and current_key and current_list:
            result[current_key] = current_list
        current_list = []
        in_list = False
        in_dict_in_list = False
        list_dict_keys = []

    def _set_value(key, value):
        nonlocal current_key
        value = value.strip().strip("'\"")
        if value.lower() in ("none", "null", ""):
            return
        if value.lower() == "true":
            value = True
        elif value.lower() == "false":
            value = False
        try:
            if "." in value:
                value = float(value)
            else:
                value = int(value)
        except (ValueError, TypeError):
            pass
        result[key] = value

    for line in yaml_block.split("\n"):
        stripped = line.strip()

        # 跳过空行和注释
        if not stripped or stripped.startswith("#"):
            continue

        # 列表项: "- item" 或 "- key: value"
        if stripped.startswith("- "):
            item = stripped[2:].strip()
            if not in_list:
                _flush_list()
                in_list = True
            # 检测 "key: value" 格式的列表项
            if ": " in item and not item.startswith(("'", '"')):
                if in_dict_in_list and current_dict:
                    current_list.append(current_dict)
                    current_dict = {}
                in_dict_in_list = True
                k, v = item.split(": ", 1)
                current_dict[k.strip()] = v.strip().strip("'\"")
            else:
                if in_dict_in_list and current_dict:
                    current_list.append(current_dict)
                    current_dict = {}
                    in_dict_in_list = False
                current_list.append(item.strip().strip("'\""))
            continue

        # 如果之前在处理 dict-in-list，需要 flush
        if in_dict_in_list and current_dict:
            current_list.append(current_dict)
            current_dict = {}
            in_dict_in_list = False

        # 子项缩进（dict-in-list 内部）
        if line.startswith("    ") or line.startswith("  "):
            if in_dict_in_list and ": " in stripped:
                k, v = stripped.split(": ", 1)
                current_dict[k.strip()] = v.strip().strip("'\"")
            continue

        # 普通键值对
        if ": " in stripped:
            _flush_list()
            key, value = stripped.split(": ", 1)
            key = key.strip()
            value = value.strip()

            if value == "" or value == "''" or value == '""':
                # 可能是列表的开始（后续行有 -）
                current_key = key
                current_list = []
                in_list = False
            else:
                _set_value(key, value)
                current_key = key

        # 只有键没有值（冒号结尾）
        elif stripped.endswith(":") and not stripped.startswith("-"):
            _flush_list()
            current_key = stripped.rstrip(":").strip()
            result[current_key] = None  # 占位

    _flush_list()

    return result


# ---- 主入口 ----

def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器"""
    parser = argparse.ArgumentParser(
        prog="utils_extract_meta",
        description=f"从 PDF/图片中提取 EPUB 元数据 (meta.yaml) v{VERSION}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    python utils_extract_meta.py book.pdf
    python utils_extract_meta.py book.pdf -m nvidia_kimi -o meta.yaml
    python utils_extract_meta.py book.pdf --pages 1-3 --dry-run
    python utils_extract_meta.py cover.png --output meta.yaml
        """.strip(),
    )
    parser.add_argument("input", help="PDF 或图片文件路径")
    parser.add_argument("-o", "--output", default=None,
                        help="输出 meta.yaml 路径（默认: 输入文件名_meta.yaml）")
    parser.add_argument("-m", "--model", default=None,
                        help="模型名称（默认: 环境变量 OCR_MODEL 或 config 默认模型）")
    parser.add_argument("--pages", default="1-3",
                        help="提取的页码范围（默认: 1-3，封面+版权页）")
    parser.add_argument("--dpi", type=int, default=200,
                        help="PDF 渲染 DPI（默认: 200）")
    parser.add_argument("--dry-run", action="store_true",
                        help="仅预览提取结果，不保存")
    parser.add_argument("--debug", action="store_true",
                        help="输出 LLM 原始响应（调试用）")
    parser.add_argument("-v", "--version", action="store_true",
                        help="显示版本信息")
    return parser


def main():
    parser = build_parser()

    if "-v" in sys.argv or "--version" in sys.argv:
        print(f"utils_extract_meta v{VERSION}")
        return

    if len(sys.argv) == 1:
        parser.print_help()
        return

    args = parser.parse_args()

    input_path = args.input
    if not os.path.exists(input_path):
        print(f"❌ 找不到: {input_path}")
        sys.exit(1)

    # 初始化库
    _init_libs()
    if not FITZ_AVAILABLE or not PIL_AVAILABLE:
        print("❌ 需要安装: pip install pymupdf pillow")
        sys.exit(1)
    if not OPENAI_AVAILABLE:
        print("⚠️  openai 库未安装，部分模型可能无法使用")
        print("   建议安装: pip install openai")

    # 加载模型配置
    try:
        from models_config import CONFIGS, DEFAULT_MODEL, load_configs

        model_key = args.model or os.environ.get("OCR_MODEL", DEFAULT_MODEL)
        if model_key not in CONFIGS:
            print(f"❌ 未知模型: {model_key}")
            print(f"可用模型: {', '.join(CONFIGS.keys())}")
            print("提示: 使用 VibeOCR.py --list-models 查看完整列表")
            sys.exit(1)

        config = CONFIGS[model_key].copy()
        api_key_env = config["api_key_env"]
        api_key = os.environ.get(api_key_env)

        try:
            import config as config_module
        except ImportError:
            config_module = None

        if not api_key and config_module:
            api_key = getattr(config_module, api_key_env, None)

        if not api_key:
            print(f"⚠️  API Key 未配置")
            print(f"   设置环境变量: export {api_key_env}=your_key")
            sys.exit(1)

        config["api_key"] = api_key
        config["model_key"] = model_key
    except ImportError as e:
        print(f"❌ 无法加载模型配置: {e}")
        sys.exit(1)

    print(f"\n📖 正在提取元数据: {input_path}")
    print(f"🤖 模型: {config.get('name', model_key)} ({model_key})")

    # PDF 转图片
    ext = os.path.splitext(input_path)[1].lower()
    if ext in (".pdf",):
        print(f"🔧 转换 PDF 页面: {args.pages}...")
        images, page_count = _pdf_to_images(input_path, args.pages, args.dpi)
        if page_count == 0:
            print("❌ 没有可处理的页面")
            sys.exit(1)
        print(f"  共 {page_count} 页")
    elif ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"):
        # 单图片处理
        import base64
        from PIL import Image
        from io import BytesIO

        img = Image.open(input_path)
        if img.width > 1600:
            ratio = 1600 / img.width
            new_h = int(img.height * ratio)
            img = img.resize((1600, new_h), Image.LANCZOS)

        buf = BytesIO()
        img.save(buf, format="PNG", optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode()
        images = [{
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{b64}"},
        }]
        print(f"  🖼️  图片已编码 ({int(len(buf.getvalue()) / 1024)}KB)")
    else:
        print(f"❌ 不支持的文件格式: {ext}")
        print("   支持的格式: .pdf .png .jpg .jpeg .webp .bmp .tiff")
        sys.exit(1)

    # 调用 LLM
    print("🔍 分析元数据...")
    try:
        raw_response = _call_llm(config, images, META_PROMPT)
    except Exception as e:
        print(f"❌ LLM 调用失败: {e}")
        sys.exit(1)

    if args.debug:
        print("\n--- LLM 原始响应 ---")
        print(raw_response)
        print("---\n")

    # 解析 YAML
    meta = _parse_yaml_response(raw_response)

    # 构建最终 YAML 字符串
    yaml_output = "---\n"
    yaml_output += "# 本文件由 utils_extract_meta v" + VERSION + " 自动生成\n"
    yaml_output += "# 请人工核对以下信息，修正可能的识别错误\n"
    yaml_output += "\n"

    # 按字段顺序输出
    field_order = [
        ("title", "书名"),
        ("author", "作者"),
        ("publisher", "出版社"),
        ("publisher_address", "出版社地址"),
        ("publisher_url", "出版社网址"),
        ("date", "出版日期"),
        ("edition", "版次"),
        ("print_run", "印次"),
    ]
    for field, comment in field_order:
        v = meta.get(field)
        if v is not None and v != "" and v != "":
            yaml_output += f"# {comment}\n"
            if isinstance(v, list):
                yaml_output += f"{field}:\n"
                for item in v:
                    yaml_output += f"  - {item}\n"
            else:
                yaml_output += f"{field}: {v}\n"
            yaml_output += "\n"

    # identifier
    isbn = meta.get("identifier") or meta.get("isbn")
    if isbn:
        yaml_output += "# ISBN\n"
        if isinstance(isbn, list) and isinstance(isbn[0], dict):
            yaml_output += "identifier:\n"
            for item in isbn:
                yaml_output += f"  - scheme: {item.get('scheme', 'ISBN-13')}\n"
                yaml_output += f"    value: {item.get('value', '')}\n"
        elif isinstance(isbn, list):
            yaml_output += "identifier:\n"
            for item in isbn:
                yaml_output += f"  - scheme: ISBN-13\n"
                yaml_output += f"    value: {item}\n"
        else:
            yaml_output += "identifier:\n"
            yaml_output += f"  - scheme: ISBN-13\n"
            yaml_output += f"    value: {isbn}\n"
        yaml_output += "\n"

    # 制作信息
    prod_fields = [("producer", "制作/排版"), ("format", "开本"), ("pages", "总页数"), ("word_count", "字数")]
    has_prod = any(meta.get(f) for f, _ in prod_fields)
    if has_prod:
        yaml_output += "# 制作信息\n"
        for field, comment in prod_fields:
            v = meta.get(field)
            if v is not None and v != "":
                yaml_output += f"{field}: {v}\n"
        yaml_output += "\n"

    # 价格
    price = meta.get("price")
    if price:
        yaml_output += "# 价格\n"
        yaml_output += f"price: {price}\n"
        yaml_output += f"price_currency: {meta.get('price_currency', 'CNY')}\n"
        yaml_output += "\n"

    # 编辑团队
    contributors = meta.get("contributor", [])
    if contributors:
        yaml_output += "# 编辑团队\n"
        yaml_output += "contributor:\n"
        for c in contributors:
            if isinstance(c, dict):
                yaml_output += f"  - role: {c.get('role', '')}\n"
                yaml_output += f"    name: {c.get('name', '')}\n"
            else:
                yaml_output += f"  - role: {c}\n"
                yaml_output += f"    name: \n"
        yaml_output += "\n"

    # 联系方式
    phone = meta.get("contact_phone") or meta.get("phone")
    if phone:
        yaml_output += "# 联系方式\n"
        yaml_output += f"contact_phone: {phone}\n\n"

    # 语言
    yaml_output += "# 语言\n"
    lang = meta.get("language", "zh-CN")
    yaml_output += f"language: {lang}\n\n"

    # 备注
    note = meta.get("note")
    if note:
        yaml_output += "# 备注\n"
        yaml_output += f"note: {note}\n"

    yaml_output = yaml_output.rstrip() + "\n"

    # 输出
    if args.dry_run:
        print("\n" + "=" * 50)
        print("📋 预览提取结果 (--dry-run)")
        print("=" * 50)
        print(yaml_output)
        print("=" * 50)
        print("💡 使用 -o meta.yaml 保存到文件")
    else:
        output_path = args.output or os.path.splitext(input_path)[0] + "_meta.yaml"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(yaml_output)
        print(f"\n✅ 元数据已保存: {output_path}")
        print(f"   {len(yaml_output)} 字符 ({len([l for l in yaml_output.split('\\n') if l.strip() and not l.startswith('#')])} 个字段)")
        print("\n💡 建议: 请人工核对提取结果，修正可能的识别错误")


if __name__ == "__main__":
    main()

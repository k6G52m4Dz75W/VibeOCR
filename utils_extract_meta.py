# -*- coding: utf-8 -*-
"""
utils_extract_meta.py — 从 PDF/图片中提取 EPUB 元数据 (meta.yaml)

利用 LLM OCR 管线（llm_ocr 模块），从书籍版权页/封面页提取结构化元数据，
输出标准的 EPUB meta.yaml 格式。

用法:
    python utils_extract_meta.py book.pdf -o meta.yaml
    python utils_extract_meta.py book.pdf --model nvidia_kimi
    python utils_extract_meta.py book.pdf --pages 1-3 --dry-run
    python utils_extract_meta.py cover.png --debug
    python utils_extract_meta.py -v
"""

import sys
import os
import re
import argparse

try:
    import version
    VERSION = version.VERSION
except ImportError:
    VERSION = "0.0.0"

import yaml


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
format:                   # 开本（如 "880毫米 × 1230毫米 1/32"）
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
        if any(ch in value for ch in (':', '#', '{', '}', '[', ']', ',', '&', '*', '?', '|', '-', '<', '>', '=', '!', '%', '@', '`')):
            escaped = value.replace('\\', '\\\\').replace('"', '\\"')
            return f'"{escaped}"'
        return value
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, dict):
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


# ---- LLM 响应解析 ----

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

    def _flush_list():
        nonlocal current_list, current_dict, in_list, in_dict_in_list
        if in_dict_in_list and current_dict:
            current_list.append(current_dict)
            current_dict = {}
        if in_list and current_key and current_list:
            result[current_key] = current_list
        current_list = []
        in_list = False
        in_dict_in_list = False

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
        if not stripped or stripped.startswith("#"):
            continue

        if stripped.startswith("- "):
            item = stripped[2:].strip()
            if not in_list:
                _flush_list()
                in_list = True
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

        if in_dict_in_list and current_dict:
            current_list.append(current_dict)
            current_dict = {}
            in_dict_in_list = False

        if line.startswith("    ") or line.startswith("  "):
            if in_dict_in_list and ": " in stripped:
                k, v = stripped.split(": ", 1)
                current_dict[k.strip()] = v.strip().strip("'\"")
            continue

        if ": " in stripped:
            _flush_list()
            key, value = stripped.split(": ", 1)
            key = key.strip()
            value = value.strip()
            if value == "" or value == "''" or value == '""':
                current_key = key
                current_list = []
                in_list = False
            else:
                _set_value(key, value)
                current_key = key
        elif stripped.endswith(":") and not stripped.startswith("-"):
            _flush_list()
            current_key = stripped.rstrip(":").strip()
            result[current_key] = None

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


def _build_output_yaml(meta: dict) -> str:
    """按 meta.yaml 规范格式构建输出字符串"""
    lines = ["---"]
    lines.append(f"# 本文件由 utils_extract_meta v{VERSION} 自动生成")
    lines.append("# 请人工核对以下信息，修正可能的识别错误")
    lines.append("")

    # 基本标识
    if meta.get("title"):
        lines.append(f"title: {meta['title']}")
        lines.append("")
    author = meta.get("author", [])
    if isinstance(author, str):
        author = [a.strip() for a in author.replace("、", ",").split(",") if a.strip()]
    if author:
        lines.append("author:")
        for a in author:
            lines.append(f"  - {a}")
        lines.append("")
    if meta.get("publisher"):
        lines.append(f"publisher: {meta['publisher']}")
        lines.append("")
    if meta.get("publisher_address"):
        lines.append(f"publisher_address: {meta['publisher_address']}")
        lines.append("")
    if meta.get("publisher_url"):
        lines.append(f"publisher_url: {meta['publisher_url']}")
        lines.append("")

    # 出版信息
    if meta.get("date"):
        lines.append(f"date: {meta['date']}")
        lines.append("")
    if meta.get("edition"):
        lines.append(f"edition: {meta['edition']}")
        lines.append("")
    if meta.get("print_run"):
        lines.append(f"print_run: {meta['print_run']}")
        lines.append("")

    # ISBN
    isbn = meta.get("identifier") or meta.get("isbn")
    if isbn:
        lines.append("identifier:")
        if isinstance(isbn, list):
            for item in isbn:
                if isinstance(item, dict):
                    lines.append(f"  - scheme: {item.get('scheme', 'ISBN-13')}")
                    lines.append(f"    value: {item.get('value', '')}")
                else:
                    lines.append(f"  - scheme: ISBN-13")
                    lines.append(f"    value: {item}")
        else:
            lines.append(f"  - scheme: ISBN-13")
            lines.append(f"    value: {isbn}")
        lines.append("")

    # 制作信息
    prod_items = []
    for f in ("producer", "format", "pages", "word_count"):
        if meta.get(f):
            prod_items.append(f"{f}: {meta[f]}")
    if prod_items:
        lines.append("# 制作信息")
        lines.extend(prod_items)
        lines.append("")

    # 价格
    if meta.get("price"):
        lines.append(f"price: {meta['price']}")
        lines.append(f"price_currency: {meta.get('price_currency', 'CNY')}")
        lines.append("")

    # 编辑团队
    contributors = meta.get("contributor", [])
    if contributors:
        lines.append("# 编辑团队")
        lines.append("contributor:")
        for c in contributors:
            if isinstance(c, dict):
                lines.append(f"  - role: {c.get('role', '')}")
                lines.append(f"    name: {c.get('name', '')}")
            else:
                lines.append(f"  - role: {c}")
                lines.append(f"    name: ")
        lines.append("")

    # 联系方式
    phone = meta.get("contact_phone") or meta.get("phone")
    if phone:
        lines.append(f"contact_phone: {phone}")
        lines.append("")

    # 语言
    lang = meta.get("language", "zh-CN")
    lines.append(f"language: {lang}")
    lines.append("")

    # 备注
    if meta.get("note"):
        lines.append(f"note: {meta['note']}")

    return "\n".join(lines) + "\n"


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

    # 从 llm_ocr 加载公共模块
    try:
        from llm_ocr import load_model_config, pdf_pages_to_b64, image_file_to_b64, call_llm
    except ImportError as e:
        print(f"❌ 请将 llm_ocr.py 放在同一目录下: {e}")
        sys.exit(1)

    # 加载模型配置
    model_key = args.model or os.environ.get("OCR_MODEL")
    config = load_model_config(model_key)
    print(f"\n📖 正在提取元数据: {input_path}")
    print(f"🤖 模型: {config.get('name', model_key)} ({config['model_key']})")

    # PDF 或图片 → base64
    ext = os.path.splitext(input_path)[1].lower()
    if ext in (".pdf",):
        print(f"🔧 转换 PDF 页面: {args.pages}...")
        images, page_count = pdf_pages_to_b64(input_path, args.dpi, page_range=args.pages)
        if page_count == 0:
            print("❌ 没有可处理的页面")
            sys.exit(1)
        print(f"  共 {page_count} 页")
    elif ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"):
        images = image_file_to_b64(input_path)
        print(f"  🖼️  单图片已编码")
    else:
        print(f"❌ 不支持的文件格式: {ext}")
        print("   支持的格式: .pdf .png .jpg .jpeg .webp .bmp .tiff")
        sys.exit(1)

    # 调用 LLM
    print("🔍 分析元数据...")
    try:
        raw_response = call_llm(config, images, META_PROMPT, verbose=True)
    except Exception as e:
        print(f"❌ LLM 调用失败: {e}")
        sys.exit(1)

    if args.debug:
        print("\n--- LLM 原始响应 ---")
        print(raw_response)
        print("---\n")

    # 解析 YAML 并构建输出
    meta = _parse_yaml_response(raw_response)
    yaml_output = _build_output_yaml(meta)

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
        field_count = len([l for l in yaml_output.split("\n") if l.strip() and not l.startswith("#") and not l.startswith("-") and ": " in l])
        print(f"\n✅ 元数据已保存: {output_path}")
        print(f"   {len(yaml_output)} 字符 ({field_count} 个字段)")
        print("\n💡 建议: 请人工核对提取结果，修正可能的识别错误")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
utils_extract_meta.py — 从 PDF/图片中提取 EPUB 元数据 (meta.yaml)

利用 LLM OCR 管线（llm_ocr 模块），从书籍版权页/封面页提取结构化元数据，
直接输出 LLM 返回的标准 YAML 内容。

设计选择：不自行解析 YAML，让 LLM 直接返回完整的 meta.yaml。
实践证明 LLM 直接输出比自建 YAML 解析器更准确、更完整。

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


# ---- 提示词 ----

META_PROMPT = """从图片提取文字，返回符合电子书 EPUB 规范的 meta.yaml 元数据。根据以下模板和说明直接返回YAML的内容，不要添加任何额外说明：
---
title: # 书名(若有副标题的话返回如下列表，否则直接返回书名）
- type: main
  text: # 书名
- type: subtitle
  text: # 副标题
creator: # 作者（若作者姓名之间包含顿号、则作为不同的作者返回列表）
- role: author
  text: # 姓名
identifier:
- scheme: ISBN-13
  text: # 去除-的13位书号
publisher: # 出版社
date: # 出版日期，格式为YYYY-MM-DD，只有年份是必须的
lang: zh-CN # 根据版权页语言判断书籍语言
contributor:
  - role: editor
    text: # 编辑姓名（若有多位则返回列表）
  - role: printer 
    text: # 印制人员姓名（若有多位则返回列表）
---
"""


# ---- LLM 响应处理 ----

def _extract_yaml_block(text: str) -> str:
    """从 LLM 响应中提取纯净的 YAML 块"""
    # 尝试提取 ```yaml ... ``` / ``` ... ``` 包裹的块
    match = re.search(r"```(?:yaml)?\s*\n(.*?)\n```", text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # 尝试提取以 --- 开头的内容
    if text.strip().startswith("---"):
        return text.strip()

    # 尝试提取包含 title: 的部分
    idx = text.find("title:")
    if idx != -1:
        # 找到 title: 前面的 ---（如果有）
        before = text[:idx].rfind("---")
        if before != -1:
            return text[before:].strip()
        return text[idx:].strip()

    # 保底：返回整个文本
    return text.strip()


def _validate_yaml(yaml_text: str) -> tuple[bool, str]:
    """对 YAML 做基本校验，返回 (是否合法, 提示信息)"""
    if not yaml_text:
        return False, "YAML 内容为空"

    # 必须以 --- 开头
    if not yaml_text.startswith("---"):
        # 尝试自动补上
        yaml_text = "---\n" + yaml_text

    # 必须包含 title
    if "title:" not in yaml_text:
        return False, "YAML 中缺少 title 字段"

    # 检查作者/创作者字段
    if "author:" not in yaml_text and "creator:" not in yaml_text:
        return True, "⚠️  缺少 author/creator 字段，建议人工补全"

    return True, ""


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
        raw_response = call_llm(config, images, META_PROMPT, verbose=False)
    except Exception as e:
        print(f"❌ LLM 调用失败: {e}")
        sys.exit(1)

    if args.debug:
        print("\n--- LLM 原始响应 ---")
        print(raw_response)
        print("---\n")

    # 提取 YAML 块并校验
    yaml_output = _extract_yaml_block(raw_response)
    valid, hint = _validate_yaml(yaml_output)

    if not valid:
        print(f"❌ YAML 校验失败: {hint}")
        print("   原始响应已保存为调试信息，建议调整 prompt 重试")
        if args.debug:
            print(f"   提取到的内容:\n{yaml_output[:500]}")
        sys.exit(1)

    if hint:
        print(f"\n{hint}")

    # 添加自动生成标记（注释形式）
    header = f"# 本文件由 utils_extract_meta v{VERSION} 自动生成\n"
    header += "# 请人工核对以下信息，修正可能的识别错误\n"
    if "---\n" in yaml_output:
        yaml_output = yaml_output.replace("---\n", "---\n" + header, 1)
    else:
        yaml_output = "---\n" + header + yaml_output

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
        field_count = len([l for l in yaml_output.split("\n") if l.strip()
                          and not l.startswith("#") and ": " in l])
        print(f"\n✅ 元数据已保存: {output_path}")
        print(f"   {len(yaml_output)} 字符 ({field_count} 个字段)")
        print("\n💡 建议: 请人工核对提取结果，修正可能的识别错误")


if __name__ == "__main__":
    main()

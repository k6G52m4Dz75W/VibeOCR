# -*- coding: utf-8 -*-
"""
utils_extract_meta.py — 从 PDF/图片中提取 EPUB 元数据 + 版权页文本

利用 LLM OCR 管线（llm_ocr 模块），一次请求完成两项任务：
  1. meta.yaml  — EPUB 标准元数据
  2. COPYRIGHT.md — 版权页原文整理成的 Markdown 表格

设计选择：不自行解析 YAML，让 LLM 直接返回完整的 meta.yaml。
COPYRIGHT.md 直接截取原始 LLM 响应后保存，不走后处理流程。

用法:
    python utils_extract_meta.py book.pdf
    python utils_extract_meta.py book.pdf -m nvidia_kimi
    python utils_extract_meta.py cover.png --dry-run
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

PROMPT = """从图书的版权页图片提取文字，识别整理后直接返回以下2项数据，不要添加任何额外说明：

第1项，符合电子书 EPUB 规范的 meta.yaml 元数据。根据以下模板和说明直接返回YAML的内容，第1项开始和结束用---标记：
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
  scheme: ISBN-13
  text: 'urn:isbn:' # 'urn:isbn:去除-的13位书号'
publisher: # 出版社
date: # 出版日期，格式为YYYY-MM-DD，只有年份是必须的
lang: zh-CN # 根据版权页语言判断书籍语言
contributor:
  - role: editor
    text: # 编辑姓名（若有多位则返回列表）
  - role: printer 
    text: # 印制人员姓名（若有多位则返回列表）
---
第2项，原始文本内容整理成的表格，左边是字段名，例如书名，作者等，右边是值，例如书的真正名字，作者的姓名等，表头留空，表格前面加上“# 出版信息”，直接返回给我符合markdown格式的文本。"""


# ---- LLM 响应拆分 ----

def _split_response(text: str) -> tuple[str, str]:
    """将 LLM 响应拆分为 (meta_yaml, copyright_text)。

    查找第一个 --- 和第二个 --- 之间的内容作为 YAML，
    第二个 --- 之后的内容作为 COPYRIGHT.md。
    """
    stripped = text.strip()

    # 定位两个 --- 分隔符
    first = stripped.find("---")
    if first == -1:
        # 没有 ---，说明 LLM 没按格式返回
        return "", stripped

    after_first = first + 3
    second = stripped.find("---", after_first)
    if second == -1:
        # 只有一个 ---（旧格式兼容），整个文本作为 YAML
        yaml_text = stripped[first:]
        return yaml_text, ""

    # 两个 --- 之间的是 YAML（跳过第一个 --- 后的换行）
    yaml_start = after_first
    while yaml_start < len(stripped) and stripped[yaml_start] in "\n\r ":
        yaml_start += 1
    yaml_text = stripped[first:second + 3]  # 包含首尾 ---

    # 第二个 --- 之后的是 COPYRIGHT
    copyright_start = second + 3
    while copyright_start < len(stripped) and stripped[copyright_start] in "\n\r ":
        copyright_start += 1
    copyright_text = stripped[copyright_start:]

    return yaml_text, copyright_text


def _validate_yaml(yaml_text: str) -> tuple[bool, str]:
    """对 YAML 做基本校验，返回 (是否合法, 提示信息)"""
    if not yaml_text:
        return False, "YAML 内容为空"

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
        description=f"从 PDF/图片提取 EPUB 元数据 + 版权页文本 v{VERSION}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    python utils_extract_meta.py book.pdf
    python utils_extract_meta.py book.pdf -m nvidia_kimi
    python utils_extract_meta.py book.pdf --dry-run
    python utils_extract_meta.py cover.png --debug
        """.strip(),
    )
    parser.add_argument("input", help="PDF 或图片文件路径")
    parser.add_argument("-o", "--output", default=None,
                        help="输出文件夹路径（默认: 输入文件所在目录），生成 meta.yaml + COPYRIGHT.md")
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


def _inject_header(yaml_text: str) -> str:
    """在 YAML 首行后插入自动生成标记"""
    header = f"# 本文件由 utils_extract_meta v{VERSION} 自动生成\n"
    header += "# 请人工核对以下信息，修正可能的识别错误\n"
    if yaml_text.startswith("---\n"):
        return yaml_text.replace("---\n", "---\n" + header, 1)
    return "---\n" + header + yaml_text


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
    print(f"\n📖 正在分析版权页: {input_path}")
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
        raw_response = call_llm(config, images, PROMPT, verbose=False)
    except Exception as e:
        print(f"❌ LLM 调用失败: {e}")
        sys.exit(1)

    if args.debug:
        print("\n--- LLM 原始响应 ---")
        print(raw_response)
        print("---\n")

    # 拆分为 YAML + COPYRIGHT
    yaml_text, copyright_text = _split_response(raw_response)
    valid, hint = _validate_yaml(yaml_text)

    if not valid:
        print(f"❌ 校验失败: {hint}")
        print("   建议调整 prompt 重试")
        if args.debug:
            print(f"   提取到的内容:\n{yaml_text[:500]}")
        sys.exit(1)

    if hint:
        print(f"\n{hint}")

    # 注入自动生成标记
    yaml_output = _inject_header(yaml_text)

    # 计算输出路径（固定文件名：meta.yaml / COPYRIGHT.md）
    def _output_paths(dir_path: str | None) -> tuple[str, str]:
        if dir_path:
            d = dir_path.rstrip("/\\")
        else:
            d = os.path.dirname(input_path) or "."
        return os.path.join(d, "meta.yaml"), os.path.join(d, "COPYRIGHT.md")
        meta_path = base
        dir_path = os.path.dirname(base)
        stem = os.path.splitext(os.path.basename(base))[0]
        copyright_path = os.path.join(dir_path, stem + "_COPYRIGHT.md")
        return meta_path, copyright_path

    meta_path, copyright_path = _output_paths(args.output)

    if args.dry_run:
        print("\n" + "=" * 50)
        print("📋 预览结果 (--dry-run)")
        print("=" * 50)
        print("--- meta.yaml ---")
        print(yaml_output)
        print("--- COPYRIGHT.md ---")
        print(copyright_text if copyright_text else "(无)")
        print("=" * 50)
        print(f"💡 保存时将生成:\n  {meta_path}\n  {copyright_path}")
    else:
        # 保存 meta.yaml
        os.makedirs(os.path.dirname(meta_path) or ".", exist_ok=True)
        with open(meta_path, "w", encoding="utf-8") as f:
            f.write(yaml_output)
        meta_fields = len([l for l in yaml_output.split("\n") if l.strip()
                          and not l.startswith("#") and ": " in l])
        print(f"\n✅ 元数据已保存: {meta_path}")
        print(f"   {len(yaml_output)} 字符 ({meta_fields} 个字段)")

        # 保存 COPYRIGHT.md（原始文本，不走后处理）
        if copyright_text:
            os.makedirs(os.path.dirname(copyright_path) or ".", exist_ok=True)
            with open(copyright_path, "w", encoding="utf-8") as f:
                f.write(copyright_text)
            print(f"✅ 版权页已保存: {copyright_path}")
            print(f"   {len(copyright_text)} 字符")

        print("\n💡 建议: 请人工核对提取结果，修正可能的识别错误")


if __name__ == "__main__":
    main()

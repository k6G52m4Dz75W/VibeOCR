# -*- coding: utf-8 -*-
"""
独立文本清理 CLI — 对已有 OCR 结果进行后处理清洗。

用法:
    python utils_clean_text.py input.txt output.txt
    python utils_clean_text.py input.txt output.txt --skip dedup
    python utils_clean_text.py -v
"""

import sys
import os
import argparse

try:
    import version
    VERSION = version.VERSION
except ImportError:
    VERSION = "0.0.0"

import postprocess


def build_parser() -> argparse.ArgumentParser:
    """构建标准命令行参数解析器"""
    parser = argparse.ArgumentParser(
        prog=os.path.basename(sys.argv[0]),
        description="独立文本清理 CLI — 对已有 OCR 结果进行后处理清洗 v" + VERSION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input", help="输入文本文件路径")
    parser.add_argument("output", help="输出文本文件路径")
    parser.add_argument("-s", "--skip", default=None,
                        help="跳过后处理模块，逗号分隔（如: dedup,fullwidth_punct）")
    parser.add_argument("-v", "--version", action="store_true",
                        help="显示版本信息")
    return parser


def main():
    parser = build_parser()

    if "-v" in sys.argv or "--version" in sys.argv:
        print(f"utils_clean_text v{VERSION}")
        return

    if len(sys.argv) == 1:
        parser.print_help()
        return

    args = parser.parse_args()

    skip_args = [s.strip() for s in args.skip.split(",")] if args.skip else []

    # 读取
    with open(args.input, "r", encoding="utf-8") as f:
        text = f.read()

    # 处理
    cleaned = postprocess.process(text, skip=skip_args)

    # 写入
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(cleaned)

    skip_info = f" (跳过: {','.join(skip_args)})" if skip_args else ""
    print(f"✅ 完成处理：{len(text)} 个字符 -> 已保存为 {args.output}{skip_info}")


if __name__ == "__main__":
    main()

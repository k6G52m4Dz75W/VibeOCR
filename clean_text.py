# -*- coding: utf-8 -*-
import sys
import postprocess


def main():
    # 解析参数
    skip_args = []
    input_file = None
    output_file = None
    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == "--skip" and i + 1 < len(sys.argv):
            skip_args = sys.argv[i + 1].split(",")
            i += 2
        elif input_file is None:
            input_file = sys.argv[i]
            i += 1
        elif output_file is None:
            output_file = sys.argv[i]
            i += 1
        else:
            i += 1

    if not input_file or not output_file:
        print("❌ 用法错误！请运行：python clean_text.py <输入文件> <输出文件> [--skip 模块名1,模块名2]")
        print("   示例：python clean_text.py input.txt output.txt --skip dedup")
        return

    # 读取
    with open(input_file, "r", encoding="utf-8") as f:
        text = f.read()

    # 处理
    cleaned = postprocess.process(text, skip=skip_args)

    # 写入
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(cleaned)

    skip_info = f" (跳过: {','.join(skip_args)})" if skip_args else ""
    print(f"✅ 完成处理：{len(text)} 个字符 -> 已保存为 {output_file}{skip_info}")


if __name__ == "__main__":
    main()
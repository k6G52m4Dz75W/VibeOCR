# -*- coding: utf-8 -*-
import sys
import postprocess

def main():
    # 直接从命令行获取输入和输出文件名
    if len(sys.argv) < 3:
        print("❌ 用法错误！请运行：python clean_text.py <输入文件> <输出文件>")
        return

    input_file = sys.argv[1]
    output_file = sys.argv[2]

    # 读取
    with open(input_file, "r", encoding="utf-8") as f:
        text = f.read()
    
    # 处理
    cleaned = postprocess.process(text)
    
    # 写入
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(cleaned)
    
    print(f"✅ 完成处理：{len(text)} 个字符 -> 已保存为 {output_file}")

if __name__ == "__main__":
    main()
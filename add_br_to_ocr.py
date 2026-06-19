#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OCR结果段落空白检测工具 - 纯几何版
基于PaddleOCR-VL JSON输出，自动检测段落分隔并插入 <br />

用法:
    python add_br_to_ocr.py input.json -o output.txt --gap-multiplier 2.5
"""

import json
import numpy as np
import re
import argparse
from pathlib import Path


def add_br_to_paragraphs(json_path: str, output_path: str = None,
                         gap_multiplier: float = 2.5) -> str:
    """
    在OCR结果的JSON中检测段落分隔并插入 <br />

    核心逻辑（纯几何，无内容规则）：
    1. 逐页提取文本块坐标
    2. 计算同页相邻块的垂直间距
    3. 用"中位间距 x gap_multiplier"作为阈值
    4. 只有间距明显大于正常的才插入 <br />

    参数:
        json_path: 输入JSON文件路径（PaddleOCR-VL格式）
        output_path: 输出文件路径（可选）
        gap_multiplier: 倍数阈值（默认2.5）
            - 1.5~2.0: 较敏感，可能检测到更多空行
            - 2.5~3.0: 适中，只检测明显的空段落  
            - 4.0+: 严格，只检测非常大的间距

    返回:
        处理后的纯文本（带<br />标记）
    """

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    ignore_labels = {'number', 'footer', 'header', 'header_image', 'footer_image',
                     'footnote', 'aside_text', 'image'}

    all_lines = []
    total_br = 0

    for page_idx, page in enumerate(data):
        parsing_list = page['prunedResult']['parsing_res_list']

        # 提取当前页文本块
        blocks = []
        for block in parsing_list:
            label = block.get('block_label', 'text')
            if label in ignore_labels:
                continue

            bbox = block['block_bbox']  # [x1, y1, x2, y2]
            content = block.get('block_content', '').strip()
            if not content:
                continue

            # 清理HTML标签
            content = re.sub(r'<[^>]+>', '', content).strip()
            if not content:
                continue

            blocks.append({
                'content': content,
                'y1': bbox[1],
                'y2': bbox[3],
            })

        if len(blocks) < 2:
            for b in blocks:
                all_lines.append(b['content'])
            continue

        # 按Y坐标排序
        blocks.sort(key=lambda b: b['y1'])

        # 计算所有相邻间距
        gaps = []
        for i in range(len(blocks) - 1):
            gap = blocks[i+1]['y1'] - blocks[i]['y2']
            gaps.append(gap)

        gaps = np.array(gaps)
        median_gap = np.median(gaps)
        threshold = median_gap * gap_multiplier

        # 输出
        for i, block in enumerate(blocks):
            if i > 0:
                gap = gaps[i-1]
                if gap > threshold:
                    all_lines.append('<br />')
                    total_br += 1

            all_lines.append(block['content'])

    result = '\n'.join(all_lines)

    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(result)
        print(f"已保存到: {output_path}")

    print(f"共处理 {len(data)} 页，插入 {total_br} 个 <br />")
    return result


def main():
    parser = argparse.ArgumentParser(description='OCR段落空白检测工具（纯几何版）')
    parser.add_argument('input', help='输入JSON文件路径')
    parser.add_argument('-o', '--output', help='输出文件路径')
    parser.add_argument('--gap-multiplier', type=float, default=2.5,
                        help='间距倍数阈值 (默认: 2.5)')

    args = parser.parse_args()

    output = args.output or str(Path(args.input).with_suffix('.txt'))

    add_br_to_paragraphs(
        json_path=args.input,
        output_path=output,
        gap_multiplier=args.gap_multiplier
    )


if __name__ == '__main__':
    main()
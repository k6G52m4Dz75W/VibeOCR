# -*- coding: utf-8 -*-
"""
OCR空白段落映射工具（修正版 v6 - 完整合并版）
- 修复模糊匹配插入点偏移问题（使用实际窗口长度）
- 移除 next_head 单独回退逻辑，强制联合验证
- 包含完整的 extract_br_positions 等基础函数
"""

import json
import sys
import numpy as np
import re
import argparse
from pathlib import Path
from difflib import SequenceMatcher

try:
    import version
    VERSION = version.VERSION
except ImportError:
    VERSION = "0.0.0"


def detect_format(data) -> tuple:
    """检测JSON格式并返回页面列表迭代器"""
    if isinstance(data, dict) and "pages" in data:
        pages = []
        for page in data["pages"]:
            result = page.get("result", {})
            layout_results = result.get("layoutParsingResults", [])
            for lr in layout_results:
                pruned = lr.get("prunedResult")
                if pruned:
                    pages.append(pruned)
        return pages, "new_format (paddleocr-vl-1.6)"

    if isinstance(data, list):
        pages = []
        for item in data:
            if "prunedResult" in item:
                pages.append(item["prunedResult"])
            elif isinstance(item, dict):
                pages.append(item)
        return pages, "old_format (PaddleOCR-VL-1.6)"

    if isinstance(data, dict) and "parsing_res_list" in data:
        return [data], "single_page_format"

    return [], "unknown_format"


def find_all_positions(text: str, target: str) -> list:
    """查找目标字符串在文本中的所有精确出现位置"""
    positions = []
    start = 0
    while True:
        idx = text.find(target, start)
        if idx == -1:
            break
        positions.append(idx)
        start = idx + 1
    return positions


def find_fuzzy_position(text: str, target: str, threshold: float = 0.8) -> tuple:
    """
    弹性窗口模糊查找
    返回: (匹配起始索引, 实际匹配窗口长度)
    未找到返回: (-1, 0)
    """
    if not target or not text:
        return -1, 0

    # 精确匹配优先
    idx = text.find(target)
    if idx != -1:
        return idx, len(target)

    target_len = len(target)
    text_len = len(text)
    if target_len > text_len:
        return -1, 0

    best_ratio = 0.0
    best_idx = -1
    best_win_len = 0

    min_win = max(1, int(target_len * 0.8))
    max_win = min(text_len, int(target_len * 1.2))

    for win_len in range(min_win, max_win + 1):
        step = max(1, win_len // 5)
        max_start = text_len - win_len
        for i in range(0, max_start + 1, step):
            window = text[i:i + win_len]
            ratio = SequenceMatcher(None, target, window).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_idx = i
                best_win_len = win_len
                if best_ratio > 0.95:
                    return best_idx, best_win_len

    if best_ratio >= threshold:
        return best_idx, best_win_len
    return -1, 0


def find_insert_position(text: str, prev_tail: str, next_head: str) -> int:
    """
    安全的位置查找：遍历所有 prev_tail 候选，逐一用 next_head 验证
    【修复】模糊匹配时使用实际窗口长度计算插入点
    """
    if not prev_tail or not text:
        return -1

    tail_len = len(prev_tail)
    head_len = len(next_head) if next_head else 0

    # 收集候选: (起始索引, 实际匹配长度)
    candidates = []

    # 精确匹配
    for idx in find_all_positions(text, prev_tail):
        candidates.append((idx, tail_len))

    # 模糊匹配补充
    if len(candidates) < 3:
        fuzzy_idx, fuzzy_win_len = find_fuzzy_position(text, prev_tail, threshold=0.75)
        if fuzzy_idx != -1 and not any(c[0] == fuzzy_idx for c in candidates):
            candidates.append((fuzzy_idx, fuzzy_win_len))

    if not candidates:
        return -1

    if not next_head:
        return candidates[0][0] + candidates[0][1]

    best_insert = -1
    best_score = 0.0

    for idx, actual_len in candidates:
        insert_idx = idx + actual_len

        check_len = min(head_len + 20, len(text) - insert_idx)
        if check_len <= 0:
            continue

        following_text = text[insert_idx:insert_idx + check_len]
        # 【修复】跳过前导空白(换行/空格/制表符),避免 next_head 较短时
        # 被插点后的 \n 拉低 head_ratio(典型场景:章节标题紧跟在段落末尾后)
        following_stripped = following_text.lstrip()
        if not following_stripped:
            continue
        head_ratio = SequenceMatcher(None, next_head, following_stripped[:head_len]).ratio()

        if head_ratio < 0.85:
            continue

        actual_next_pos = text.find(next_head[:20], insert_idx)
        if actual_next_pos != -1:
            gap = actual_next_pos - insert_idx
            if gap > 200:
                continue

        if head_ratio > best_score:
            best_score = head_ratio
            best_insert = insert_idx

    return best_insert


def extract_br_positions(ocr_json_path: str, gap_multiplier: float = 4.0) -> list:
    """从OCR JSON中提取空白段落的位置锚点"""
    with open(ocr_json_path, 'r', encoding='utf-8') as f:
        raw_data = json.load(f)

    pages, format_name = detect_format(raw_data)
    print(f"  检测到格式: {format_name}, 共 {len(pages)} 页")

    ignore_labels = {'number', 'footer', 'header', 'header_image', 'footer_image',
                     'footnote', 'aside_text', 'image'}

    br_positions = []

    for page_idx, page in enumerate(pages):
        parsing_list = page.get('parsing_res_list', [])
        if not parsing_list:
            continue

        blocks = []
        for block in parsing_list:
            label = block.get('block_label', 'text')
            if label in ignore_labels:
                continue
            bbox = block.get('block_bbox')
            if not bbox or len(bbox) < 4:
                continue
            content = block.get('block_content', '').strip()
            if not content:
                continue
            content = re.sub(r'<[^>]+>', '', content).strip()
            if not content:
                continue
            blocks.append({
                'content': content,
                'y1': bbox[1],
                'y2': bbox[3],
            })

        if len(blocks) < 2:
            continue

        blocks.sort(key=lambda b: b['y1'])
        gaps = [blocks[i+1]['y1'] - blocks[i]['y2'] for i in range(len(blocks) - 1)]

        if not gaps:
            continue

        gaps_arr = np.array(gaps)
        median_gap = np.median(gaps_arr)
        if median_gap == 0:
            median_gap = np.mean(gaps_arr)
            if median_gap == 0:
                median_gap = 10

        threshold = median_gap * gap_multiplier

        for i in range(len(blocks) - 1):
            if gaps[i] > threshold:
                prev_text = blocks[i]['content']
                next_text = blocks[i+1]['content']
                br_positions.append({
                    'prev_tail': prev_text[-80:],
                    'next_head': next_text[:80],
                    'page': page_idx,
                })

    return br_positions


def insert_br_into_llm_text(llm_text: str, br_positions: list) -> tuple:
    """在大模型文本中安全插入换行符"""
    insert_points = []
    failed = []

    for pos in br_positions:
        prev_tail = pos['prev_tail']
        next_head = pos['next_head']

        insert_idx = find_insert_position(llm_text, prev_tail, next_head)

        if insert_idx != -1:
            context_start = max(0, insert_idx - 30)
            context_end = min(len(llm_text), insert_idx + 30)
            # 【优化】拆分上下文并转义换行符显示
            prev_context = llm_text[context_start:insert_idx].replace('\n', '\\n')
            next_context = llm_text[insert_idx:context_end].replace('\n', '\\n')
            
            print(f"   ✓ 插入位置: {insert_idx}")
            print(f"     上文: ...{prev_context}")
            print(f"     下文: {next_context}...")

            insert_points.append(insert_idx)
        else:
            # 失败信息也同步转义，避免破坏控制台排版
            safe_tail = prev_tail[-40:].replace('\n', '\\n')
            safe_head = next_head[:40:].replace('\n', '\\n') if next_head else ""
            print(f"   ✗ 未匹配到 -> ...{safe_tail} | {safe_head}...")

    # 去重并排序（从后往前插入）
    insert_points = sorted(set(insert_points), reverse=True)

    result = llm_text
    for insert_idx in insert_points:
        if 0 <= insert_idx <= len(result):
            result = result[:insert_idx] + '\n' + result[insert_idx:]

    return result, len(insert_points), len(failed)


def main():
    parser = argparse.ArgumentParser(
        prog="utils_map_p_br",
        description=f'OCR空白段落映射工具 v{VERSION}'
    )
    parser.add_argument('ocr_json', help='OCR结果JSON文件路径')
    parser.add_argument('llm_txt', help='大模型提取的文本文件路径')
    parser.add_argument('-o', '--output', help='输出文件路径')
    parser.add_argument('--gap-multiplier', type=float, default=4.0,
                        help='OCR空白检测倍数阈值 (默认: 4.0)')
    parser.add_argument('-v', '--version', action='store_true',
                        help='显示版本信息')

    if "--version" in sys.argv or "-v" in sys.argv:
        print(f"utils_map_p_br v{VERSION}")
        return

    args = parser.parse_args()

    with open(args.llm_txt, 'r', encoding='utf-8') as f:
        llm_text = f.read()
    print(f"大模型文本: {len(llm_text)} 字符")

    print(f"\n从OCR提取空白位置 (gap_multiplier={args.gap_multiplier})...")
    br_positions = extract_br_positions(args.ocr_json, args.gap_multiplier)
    print(f"检测到 {len(br_positions)} 处空白段落")

    print(f"\n映射到大模型文本...")
    result, inserted, failed_count = insert_br_into_llm_text(llm_text, br_positions)

    output = args.output or str(Path(args.llm_txt).with_suffix('.with_br.txt'))
    with open(output, 'w', encoding='utf-8') as f:
        f.write(result)

    print(f"\n成功插入 {inserted} 个换行符")
    if failed_count > 0:
        print(f"⚠️  失败 {failed_count} 处（已跳过，未做任何回退插入）")
    print(f"已保存到: {output}")


if __name__ == '__main__':
    main()
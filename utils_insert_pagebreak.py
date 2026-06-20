# -*- coding: utf-8 -*-
"""
根据 raw 的分页标记，把分页 <span /> 标签嵌入校对文本中。
借鉴模糊匹配 + 联合验证思路。

核心实现：把处理过换行的文本和 anchor 中的换行归一化（删除）后做匹配，
再把匹配位置通过位置映射回处理过换行的文本。这样能容忍 raw 段间空行（\n\n）
与处理过换行的文本段间单换行（\n）之间的差异。
"""

import re
import sys
import argparse
from pathlib import Path
from difflib import SequenceMatcher

try:
    import version
    VERSION = version.VERSION
except ImportError:
    VERSION = "0.0.0"


# ---------- 锚点与匹配的参数 ----------
HEAD_ANCHOR_LEN = 30          # 页面头部用作锚点的字符数
TAIL_ANCHOR_LEN = 30          # 页面尾部用作锚点的字符数
FUZZY_THRESHOLD = 0.72        # 模糊匹配最低相似度
HEAD_VERIFY_WINDOW = 60       # 找到 tail 后，用 P_{i+1} head 在 tail 之后做联合验证的最大窗口

# OCR 输出中常见的水印/页脚词（单独成行或紧跟内容）
WATERMARK_SET = {
    '风眼', '风眠', '风眸', '风语', '风起', '风云', '风铃', '风语者',
}


# ---------- raw 解析 ----------
PAGE_HEADER_RE = re.compile(
    r'={40,}\s*\n第\s*(\d+)\s*页\s*\(共\s*(\d+)\s*页\)\s*\n[=\s]*\n+'
)


def parse_raw_pages(raw_text: str) -> list:
    """
    把 raw 文本按页码切分。
    返回 [{'num': 1, 'content': '...'}, ...]
    """
    pages = []
    matches = list(PAGE_HEADER_RE.finditer(raw_text))
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw_text)
        content = raw_text[start:end].rstrip('\n')
        pages.append({'num': int(m.group(1)), 'content': content})
    return pages


def strip_page_artifacts(content: str) -> str:
    """
    清理 raw 页面内容里常见的水印/页脚词（如 '风眼' '风眠'）。
    规则：单独成行（去掉首尾空白后）且属于水印集合的行整行删除。
    """
    cleaned_lines = []
    for line in content.split('\n'):
        if line.strip() in WATERMARK_SET:
            continue
        cleaned_lines.append(line)
    return '\n'.join(cleaned_lines)


# ---------- 文本扁平化（删除换行） + 位置映射 ----------
def flatten_with_map(text: str) -> tuple:
    """
    删除 text 中的所有 '\n'，同时构造一个映射：
    flat_pos -> orig_pos（orig 文本中对应的位置）。
    """
    parts = text.split('\n')
    flat = ''.join(parts)
    # 对 orig 中每个位置 i（0..len(text)-1），找对应的 flat_pos
    # 简化做法：分段累加
    pos_map = []   # flat_pos 对应的 orig 位置
    orig_pos = 0
    for part in parts:
        for _ in part:
            pos_map.append(orig_pos)
            orig_pos += 1
        orig_pos += 1   # 跳过那个 '\n'
    return flat, pos_map


def map_flat_to_orig(flat_pos: int, pos_map: list) -> int:
    """把 flat 位置映射回 orig 位置。flat_pos 超出范围时返回最后一个 orig 位置。"""
    if flat_pos >= len(pos_map):
        return pos_map[-1] if pos_map else 0
    return pos_map[flat_pos]


# ---------- anchor 提取 ----------
def make_anchors(content: str) -> tuple:
    """
    返回 (head_anchor, tail_anchor)。
    anchor 中**保留换行**，匹配时再做扁平化。
    """
    s = content.strip()
    if not s:
        return '', ''
    # 取前后片段（不删除换行），以免破坏 anchor 跟 br 文本的对应关系
    head = s[:HEAD_ANCHOR_LEN]
    tail = s[-TAIL_ANCHOR_LEN:] if len(s) > TAIL_ANCHOR_LEN else s
    return head, tail


# ---------- 模糊匹配（基于扁平化文本） ----------
def find_fuzzy_in_flat(flat_text: str, anchor_with_nl: str,
                       start_flat: int = 0,
                       threshold: float = FUZZY_THRESHOLD) -> tuple:
    """
    在 flat_text 中从 start_flat 开始查找 anchor_with_nl 的对应位置。
    anchor 内的换行视为可选（即在 flat_text 中匹配时可跳过 0~2 个字符的差异）。
    返回 (匹配起始位置 in flat_text, 实际匹配窗口长度)。
    """
    # anchor 扁平化
    flat_anchor = anchor_with_nl.replace('\n', '')
    if not flat_anchor or start_flat >= len(flat_text):
        return -1, 0

    # 精确匹配
    idx = flat_text.find(flat_anchor, start_flat)
    if idx != -1:
        return idx, len(flat_anchor)

    anchor_len = len(flat_anchor)
    text_len = len(flat_text)
    if start_flat + anchor_len > text_len:
        return -1, 0

    best_ratio = 0.0
    best_idx = -1
    best_win_len = 0

    min_win = max(1, int(anchor_len * 0.8))
    max_win = min(text_len - start_flat, int(anchor_len * 1.2))

    for win_len in range(min_win, max_win + 1):
        step = max(1, win_len // 5)
        max_i = text_len - win_len
        i = start_flat
        while i <= max_i:
            window = flat_text[i:i + win_len]
            ratio = SequenceMatcher(None, flat_anchor, window).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_idx = i
                best_win_len = win_len
                if best_ratio > 0.95:
                    return best_idx, best_win_len
            i += step

    if best_ratio >= threshold:
        return best_idx, best_win_len
    return -1, 0


# ---------- 定位分页边界 ----------
def locate_page_boundary_orig(br_text: str, br_flat: str, br_map: list,
                              prev_tail: str, next_head: str,
                              search_from_orig: int) -> int:
    """
    找到 P_i 末尾（即 P_{i+1} 开头之前）在 br_text 中的位置。
    返回 orig 位置（即 br_text 中的索引）。
    """
    if not prev_tail:
        return -1

    # search_from_orig -> search_from_flat
    search_from_flat = _orig_to_flat_pos(search_from_orig, br_map, br_text)
    search_from_flat = max(0, search_from_flat)

    flat_idx, win_len = find_fuzzy_in_flat(br_flat, prev_tail, start_flat=search_from_flat)
    if flat_idx == -1:
        return -1

    insert_at_flat = flat_idx + win_len
    insert_at_orig = map_flat_to_orig(insert_at_flat, br_map)

    # 联合验证：插入点之后的内容应当和 next_head 相符
    if next_head:
        flat_next = next_head.replace('\n', '')
        probe = br_flat[insert_at_flat: insert_at_flat + HEAD_VERIFY_WINDOW + len(flat_next)]
        if probe:
            ratio = SequenceMatcher(None, flat_next, probe[:len(flat_next) + 10]).ratio()
            if ratio < 0.55:
                # 验证失败，尝试在 search_from_flat 之后找 prev_tail 精确出现（扁平版）
                for alt in _find_all_exact_flat(br_flat, prev_tail, start_flat=search_from_flat):
                    if abs(alt - flat_idx) < 200 and alt != flat_idx:
                        new_insert_flat = alt + len(prev_tail.replace('\n', ''))
                        probe2 = br_flat[new_insert_flat: new_insert_flat + HEAD_VERIFY_WINDOW + len(flat_next)]
                        if probe2:
                            r2 = SequenceMatcher(
                                None, flat_next, probe2[:len(flat_next) + 10]
                            ).ratio()
                            if r2 > ratio:
                                flat_idx, win_len, insert_at_flat, ratio = alt, len(prev_tail.replace('\n', '')), new_insert_flat, r2
                                if ratio > 0.7:
                                    insert_at_orig = map_flat_to_orig(insert_at_flat, br_map)
                                    return insert_at_orig
                # 接受第一次的匹配（fuzzy 阈值已通过）

    return insert_at_orig


def _orig_to_flat_pos(orig_pos: int, br_map: list, br_text: str) -> int:
    """把 orig 位置转换为 flat 位置。orig_pos 处的 '\n' 不计入 flat。"""
    if orig_pos <= 0:
        return 0
    if not br_map:
        return 0
    # 找 br_map 中最大的 i 使得 br_map[i] < orig_pos
    # 然后 i+1 就是对应的 flat_pos
    lo, hi = -1, len(br_map) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if br_map[mid] < orig_pos:
            lo = mid
        else:
            hi = mid - 1
    return lo + 1   # +1 是因为我们要找的是 flat 索引 = 下一个字符的位置


def _find_all_exact_flat(flat_text: str, anchor_with_nl: str, start_flat: int = 0) -> list:
    """返回 anchor 的扁平版本在 flat_text 中从 start_flat 开始的所有精确出现位置。"""
    flat_anchor = anchor_with_nl.replace('\n', '')
    positions = []
    i = start_flat
    while True:
        j = flat_text.find(flat_anchor, i)
        if j == -1:
            break
        positions.append(j)
        i = j + 1
    return positions


# ---------- 插入 EPUB 分页符 ----------
# EPUB 规范的分页符是一个自闭合的 <span>，只出现在页面的最开头处。
# 含义：这里是某页的开始。中间页不需要闭合标签。
# 格式参照 IDPF EPUB3 / W3C Web Publications：
#   <span id="pageN" class="page-break" epub:type="pagebreak"
#         role="doc-pagebreak" aria-label="N"></span>
EPUB_PAGEBREAK_TEMPLATE = (
    '<span id="page{num}" class="page-break" '
    'epub:type="pagebreak" role="doc-pagebreak" '
    'aria-label="{num}"></span>'
)


def build_page_divs(br_text: str, pages: list, start_page: int = 1) -> tuple:
    """
    根据 pages 的 head/tail 锚点，定位每页边界并在每页最开头插入
    EPUB 规范的分页符 <span>。

    参数:
        br_text: 校对后的纯文本
        pages: raw 中解析出的页面列表
        start_page: 第一个 <span> 标签使用的页码（默认 1）。
            例如 start_page=23 且共 28 页，生成的 id 为 page23..page50。

    返回:
        (result_text, page_spans)
    """
    n = len(pages)

    # 1) 准备每页的 head/tail 锚点（保留换行）
    anchors = []
    for p in pages:
        cleaned = strip_page_artifacts(p['content'])
        head, tail = make_anchors(cleaned)
        anchors.append((head, tail, cleaned))

    # 2) 扁平化 br 文本
    br_flat, br_map = flatten_with_map(br_text)

    # 3) 前向扫描确定每页边界（只需要 start_pos，每个分页符插在页面开头）
    page_spans = []  # [(raw_page_num, start_pos_orig, end_pos_orig), ...]
    search_from_orig = 0

    for i, (head, tail, _content) in enumerate(anchors):
        if i == 0:
            start_pos_orig = 0
        else:
            head_idx_flat, head_win_flat = find_fuzzy_in_flat(
                br_flat, head,
                start_flat=_orig_to_flat_pos(search_from_orig, br_map, br_text)
            )
            if head_idx_flat == -1:
                start_pos_orig = search_from_orig
            else:
                start_pos_orig = map_flat_to_orig(head_idx_flat, br_map)

        if i < n - 1:
            next_head = anchors[i + 1][0]
            end_pos_orig = locate_page_boundary_orig(
                br_text, br_flat, br_map, tail, next_head, start_pos_orig
            )
            if end_pos_orig == -1 or end_pos_orig <= start_pos_orig:
                end_pos_orig = start_pos_orig + len(head.replace('\n', ''))
            search_from_orig = end_pos_orig
        else:
            end_pos_orig = len(br_text)

        page_spans.append((pages[i]['num'], start_pos_orig, end_pos_orig))

    # 4) 从后往前插入分页符 <span>（每个 page 一个，插在该页最开头）。
    #    因为是自闭合标签且互不嵌套，倒序插入即可保证前面已插入的位置不会被后续操作破坏。
    result = br_text
    for i in range(n - 1, -1, -1):
        page_num = i + start_page
        marker = EPUB_PAGEBREAK_TEMPLATE.format(num=page_num)
        insert_pos = page_spans[i][1]   # 该页的 start_pos
        result = result[:insert_pos] + marker + result[insert_pos:]

    return result, page_spans


# ---------- 主入口 ----------
def main():
    global HEAD_ANCHOR_LEN, TAIL_ANCHOR_LEN, FUZZY_THRESHOLD
    parser = argparse.ArgumentParser(
        prog="utils_insert_pagebreak",
        description=f'根据 raw 分页标记，在 br 校对文本中插入 EPUB 规范的分页符 <span>。v{VERSION}'
    )
    parser.add_argument('raw_txt', help='带分页标记的 OCR 原始文本')
    parser.add_argument('br_txt', help='校对后的最终文本')
    parser.add_argument('-o', '--output',
                        help='输出文件路径（默认在 br_txt 同目录下加 _div 后缀）')
    parser.add_argument('--head-len', type=int, default=HEAD_ANCHOR_LEN,
                        help=f'页面头部锚点长度（默认 {HEAD_ANCHOR_LEN}）')
    parser.add_argument('--tail-len', type=int, default=TAIL_ANCHOR_LEN,
                        help=f'页面尾部锚点长度（默认 {TAIL_ANCHOR_LEN}）')
    parser.add_argument('--threshold', type=float, default=FUZZY_THRESHOLD,
                        help=f'模糊匹配阈值（默认 {FUZZY_THRESHOLD}）')
    parser.add_argument('--start-page', type=int, default=1,
                        help='起始页码：第一个分页符使用的页码（默认 1）。'
                             '例如 --start-page 23 且共 28 页时，id 为 page23…page50。')
    parser.add_argument('-v', '--version', action='store_true',
                        help='显示版本信息')

    if "--version" in sys.argv or "-v" in sys.argv:
        print(f"utils_insert_pagebreak v{VERSION}")
        return

    args = parser.parse_args()

    HEAD_ANCHOR_LEN = args.head_len
    TAIL_ANCHOR_LEN = args.tail_len
    FUZZY_THRESHOLD = args.threshold
    start_page = args.start_page

    raw_text = Path(args.raw_txt).read_text(encoding='utf-8')
    br_text = Path(args.br_txt).read_text(encoding='utf-8')

    print(f"raw 文本: {len(raw_text)} 字符")
    print(f"br  文本: {len(br_text)} 字符")

    pages = parse_raw_pages(raw_text)
    print(f"检测到 {len(pages)} 页")

    if not pages:
        print("❌ 未找到任何分页标记，请检查 raw 文件格式")
        return

    # 打印每页的首尾锚点
    print("\n各页锚点：")
    for p in pages:
        cleaned = strip_page_artifacts(p['content'])
        head, tail = make_anchors(cleaned)
        head_disp = head[:20].replace('\n', '⏎')
        tail_disp = tail[-20:].replace('\n', '⏎')
        print(f"  P{p['num']:>2}: head=「{head_disp}」  tail=「{tail_disp}」")

    print("\n定位分页边界并插入 EPUB 分页符...")
    result, page_spans = build_page_divs(br_text, pages, start_page=start_page)

    end_page = start_page + len(pages) - 1
    print(f"  起始页码: page{start_page}，结束页码: page{end_page}（共 {len(pages)} 页）")

    print("\n各页定位结果：")
    for i, (num, start, end) in enumerate(page_spans):
        page_num = start_page + i
        preview_start = result[max(0, start):start + 25].replace('\n', '⏎')
        preview_end = result[max(0, end - 25):end].replace('\n', '⏎')
        print(f"  page{page_num:<3} [span@{start}]: tail=「{preview_end}」")

    # 默认输出路径
    if args.output:
        out_path = Path(args.output)
    else:
        br_path = Path(args.br_txt)
        out_path = br_path.with_name(br_path.stem + '_div' + br_path.suffix)

    out_path.write_text(result, encoding='utf-8')
    print(f"\n✅ 已保存到: {out_path}")
    print(f"   输出文本总字符数: {len(result)}")


if __name__ == '__main__':
    main()

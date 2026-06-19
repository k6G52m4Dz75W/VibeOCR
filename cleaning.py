# -*- coding: utf-8 -*-
"""
清理模块：处理文本的格式规范化。
包含清除批次标记、合并空行、清理空白字符。
"""

import re

def remove_ocr_grounding(text):
    return re.sub(
        r'^\s*<\|ref\|>(.*?)<\|/ref\|>\s*<\|det\|>\[\[.*?\]\]<\|/det\|>\s*$',
        '',
        text,
        flags=re.MULTILINE
    )

def remove_page_markers(text):
    """清除 ===第n页 共n页=== 的页标记（兼容旧格式）"""
    return re.sub(
        r'\n={10,}\s*\n\s*第\s*\d+\s*页\s*\(共\s*\d+\s*页\)\s*\n\s*={10,}\s*\n*',
        '\n\n',
        text,
        flags=re.MULTILINE
    )

def remove_batch_markers(text):
    """清除 ===批次n (共m批)=== 的批次标记"""
    return re.sub(
        r'^={10,}\s*\n\s*批次\s*\d+\s*\(共\s*\d+\s*批\)\s*\n={10,}\s*$',
        '',
        text,
        flags=re.MULTILINE
    )

def merge_empty_lines(text):
    """合并多余空行：2个以上连续换行只保留1个"""
    has_crlf = "\r\n" in text
    if has_crlf:
        text = re.sub(r'(\r\n){2,}', '\r\n', text)
    else:
        text = re.sub(r'\n{2,}', '\n', text)
    return text

def remove_whitespace(text):
    """清理行首行尾空白"""
    if "\r\n" in text:
        lines = text.split("\r\n")
        lines = [line.rstrip() for line in lines]
        return "\r\n".join(lines)
    else:
        lines = text.split("\n")
        lines = [line.rstrip() for line in lines]
        return "\n".join(lines)

def remove_interspersed_spaces(text: str) -> str:
    """
    删除中文文章里夹杂的英文空格，保留英文单词间的空格。

    规则（针对每个半角空格）：
    1. 空格两侧有中文字符 → 删除
    2. 两侧都是数字 → 删除
    3. 其他情况（英文-英文、英文-数字、英文-标点等）→ 保留
    4. 首尾空格直接删除
    """
    # 中文字符范围：基本汉字 + 中文标点（全角符号）
    def is_chinese(c: str) -> bool:
        return ('\u4e00' <= c <= '\u9fff' or
                '\u3000' <= c <= '\u303f' or
                '\uff00' <= c <= '\uffef')

    def is_digit(c: str) -> bool:
        return '0' <= c <= '9'

    chars = list(text)
    n = len(chars)
    to_delete = [False] * n

    for i, ch in enumerate(chars):
        if ch != ' ':
            continue

        # 向左找第一个非空格字符
        left = i - 1
        while left >= 0 and chars[left] == ' ':
            left -= 1
        # 向右找第一个非空格字符
        right = i + 1
        while right < n and chars[right] == ' ':
            right += 1

        # 边界空格直接删除
        if left < 0 or right >= n:
            to_delete[i] = True
            continue

        left_char = chars[left]
        right_char = chars[right]

        # 规则：只要有一侧是中文 → 删除
        if is_chinese(left_char) or is_chinese(right_char):
            to_delete[i] = True
        # 两侧都是数字 → 删除
        elif is_digit(left_char) and is_digit(right_char):
            to_delete[i] = True
        # 其余情况保留（不做标记）

    # 构建结果字符串
    result_chars = [chars[i] for i in range(n) if not to_delete[i]]
    return ''.join(result_chars)
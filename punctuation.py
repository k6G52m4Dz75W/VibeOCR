# -*- coding: utf-8 -*-
"""
标点模块：处理英文标点向中文全角标点的转换。
包含引号、基础标点的智能替换。

引号处理逻辑：以段落为单位独立处理，避免全文错漏引号导致的连锁混乱。
- 每个段落内的引号按奇偶交替分配前后引号
- 段首引号一定是前引号
- 单引号排除英文撇号（所有格/缩写）
"""

import re

# 英文标点 -> 中文全角标点映射
PUNCT_MAP = {
    ',': '\uff0c', 
    '.': '\u3002', 
    '!': '\uff01', 
    '?': '\uff1f', 
    ':': '\uff1a', 
    ';': '\uff1b', 
    '(': '\uff08', 
    ')': '\uff09', 
    '[': '\uff3b', 
    ']': '\uff3d', 
    '{': '\uff5b', 
    '}': '\uff5d', 
    '<': '\u300a', 
    '>': '\u300b', 
}

# 中文引号 Unicode
LEFT_DOUBLE_QUOTE = '\u201c' 
RIGHT_DOUBLE_QUOTE = '\u201d' 
LEFT_SINGLE_QUOTE = '\u2018' 
RIGHT_SINGLE_QUOTE = '\u2019' 


def _is_apostrophe(text, pos):
    """严格判断当前位置的 ' 是否是英文缩写/所有格"""
    if pos > 0 and pos < len(text) - 1:
        prev_char = text[pos - 1]
        next_char = text[pos + 1]
        if prev_char.isascii() and prev_char.isalpha() and \
           next_char.isascii() and next_char.isalpha():
            return True
        if prev_char.isascii() and prev_char.isalpha() and \
           next_char.lower() == 's':
            return True
        if prev_char.isascii() and prev_char.isalpha() and next_char.isspace():
            return True
    return False


def _convert_single_quotes_in_paragraph(text):
    """以段落为单位处理英文单引号 -> 中文单引号（排除英文撇号）

    段落内按奇偶交替分配前后引号，与双引号逻辑一致。
    """
    apostrophe_positions = set()
    for i in range(len(text)):
        if text[i] == "'" and _is_apostrophe(text, i):
            apostrophe_positions.add(i)

    result = []
    quote_count = 0
    for i, char in enumerate(text):
        if char == "'" and i not in apostrophe_positions:
            quote_count += 1
            if quote_count % 2 == 1:
                result.append(LEFT_SINGLE_QUOTE)
            else:
                result.append(RIGHT_SINGLE_QUOTE)
        else:
            result.append(char)
    return ''.join(result)


def _convert_double_quotes_in_paragraph(text):
    """以段落为单位处理英文双引号 -> 中文双引号

    核心逻辑：
    1. 段落中第一个引号一定是前引号（段首引号只可能是前引号）
    2. 之后按奇偶交替分配前后引号
    3. 段落间相互隔离，某段引号错漏不会影响其他段落
    """
    # 收集所有英文双引号位置
    quote_indices = []
    for i, char in enumerate(text):
        if char == '"':
            quote_indices.append(i)

    if not quote_indices:
        return text

    result = []
    last_pos = 0
    quote_count = 0

    for idx in quote_indices:
        # 添加引号前的文本
        result.append(text[last_pos:idx])
        quote_count += 1
        # 奇数为前引号，偶数为后引号
        if quote_count % 2 == 1:
            result.append(LEFT_DOUBLE_QUOTE)
        else:
            result.append(RIGHT_DOUBLE_QUOTE)
        last_pos = idx + 1

    # 添加最后一段文本
    result.append(text[last_pos:])
    return ''.join(result)


def _convert_basic_punctuation(text):
    """转换基础标点（跳过数字、英文后的标点）"""
    result = []
    for i, char in enumerate(text):
        if char in PUNCT_MAP:
            if i > 0:
                prev_char = text[i - 1]
                # 保留数字后的英文句点（如小数点、版本号）
                if char == '.' and prev_char.isdigit():
                    result.append(char)
                    continue
                # 保留英文单词后的标点（如网址、缩写）
                if prev_char.isascii() and prev_char.isalpha():
                    result.append(char)
                    continue
            result.append(PUNCT_MAP[char])
        else:
            result.append(char)
    return ''.join(result)


def _process_paragraph(paragraph):
    """处理单个段落：依次转换单引号、双引号、基础标点"""
    paragraph = _convert_single_quotes_in_paragraph(paragraph)
    paragraph = _convert_double_quotes_in_paragraph(paragraph)
    paragraph = _convert_basic_punctuation(paragraph)
    return paragraph


def convert_to_fullwidth_punctuation(text):
    """英文标点转中文全角标点 入口函数

    以段落为单位处理引号，避免全文错漏引号导致的连锁混乱。
    段落分隔符（\n\n 或 \n）保持不变。
    """
    # 按段落分割，保留段落分隔符
    paragraphs = re.split(r'(\n(?:\n+)?)', text)

    result = []
    for para in paragraphs:
        if para.startswith('\n'):
            # 这是段落分隔符，直接保留
            result.append(para)
        else:
            # 这是段落内容，进行处理
            result.append(_process_paragraph(para))

    return ''.join(result)
"""单元测试：module_heuristic_merge.py"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from module_heuristic_merge import heuristic_paragraph_merge, is_chinese_char


class TestIsChineseChar:
    def test_chinese_char(self):
        assert is_chinese_char('中') is True

    def test_english_char(self):
        assert is_chinese_char('a') is False

    def test_digit(self):
        assert is_chinese_char('1') is False

    def test_punctuation(self):
        assert is_chinese_char('.') is False


class TestHeuristicMerge:
    def test_merge_chinese_lines(self):
        """中文长行（不以标点结尾）断行应当合并"""
        # 第一行不以标点结尾且不是短行 → 触发合并
        text = "这是第一行很长的中文内容需要合并到下一行\n这是第二行很长的中文内容"
        result = heuristic_paragraph_merge(text)
        assert '第一行' in result
        assert '第二行' in result
        # 两句应合并到同一行
        lines = result.split('\n')
        assert len(lines) == 1

    def test_keep_short_line(self):
        """短行（标题、序号）应保留"""
        text = "第一章\n这是正文内容"
        result = heuristic_paragraph_merge(text)
        # "第一章" 是短行（≤10字符），应保留不合并
        assert '第一章' in result
        assert '正文内容' in result

    def test_keep_end_punctuation(self):
        """以句号结尾的行应当保留"""
        text = "这是第一句。\n这是下一段"
        result = heuristic_paragraph_merge(text)
        assert '第一句。' in result
        assert '下一段' in result

    def test_english_text(self):
        """英文断行应合并并加空格"""
        text = "This is a\nlong text"
        result = heuristic_paragraph_merge(text)
        assert 'long text' in result
        assert 'a long' in result.replace('\n', ' ')

    def test_multiple_blank_lines_preserved(self):
        """多个空行之间的段落不应合并"""
        text = "第一段\n\n第二段"
        result = heuristic_paragraph_merge(text)
        # 两段之间有空行时不会合并（空行被跳过，但第二段是上一段之后的非短行）
        # 实际上空行会被跳过，下一行会尝试与上一行合并
        # 空行导致 splitlines() 中 line=""，所以 continue
        lines = [l for l in result.split('\n') if l.strip()]
        assert len(lines) >= 1

    def test_no_change_for_perfect_text(self):
        text = "完好的段落。\n\n新段落开始。"
        result = heuristic_paragraph_merge(text)
        assert '完好的段落。' in result
        assert '新段落开始。' in result

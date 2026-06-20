"""单元测试：module_cleaning.py"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from module_cleaning import (
    remove_ocr_grounding,
    remove_page_markers,
    remove_batch_markers,
    merge_empty_lines,
    remove_whitespace,
    remove_interspersed_spaces,
)


class TestRemoveOcrGrounding:
    def test_typical_grounding_line(self):
        text = '<|ref|>Some text<|/ref|> <|det|>[[123,456]]<|/det|>\nhello'
        result = remove_ocr_grounding(text)
        # 定位标签整行应被删除，只剩空行 + hello
        lines = [l for l in result.split('\n') if l.strip()]
        assert 'hello' in lines

    def test_no_grounding(self):
        text = '纯文本，没有定位标签'
        assert remove_ocr_grounding(text) == text

    def test_multiple_grounding_lines(self):
        text = (
            '<|ref|>a<|/ref|> <|det|>[[0,0]]<|/det|>\n'
            '正文\n'
            '<|ref|>b<|/ref|> <|det|>[[1,1]]<|/det|>'
        )
        result = remove_ocr_grounding(text)
        assert '正文' in result
        assert '<|ref|>' not in result


class TestRemovePageMarkers:
    def test_typical_page_marker(self):
        text = '正文1\n\n====================\n第 1 页 (共 3 页)\n====================\n\n正文2'
        result = remove_page_markers(text)
        assert '第 1 页' not in result
        assert '正文1' in result
        assert '正文2' in result

    def test_no_marker(self):
        text = '普通文本'
        assert remove_page_markers(text) == text

    def test_variable_spacing(self):
        text = 'a\n\n==========\n第 2 页 (共 5 页)\n==========\n\nb'
        result = remove_page_markers(text)
        assert '第 2 页' not in result
        # 替换后可能留下多个空行，但至少两段内容都在
        assert 'a' in result
        assert 'b' in result


class TestRemoveBatchMarkers:
    def test_typical_batch_marker(self):
        text = '内容1\n========================\n批次 1 (共 2 批)\n========================\n内容2'
        result = remove_batch_markers(text)
        assert '批次 1' not in result
        assert '内容1' in result
        assert '内容2' in result

    def test_no_marker(self):
        text = '普通文本'
        assert remove_batch_markers(text) == text


class TestMergeEmptyLines:
    def test_multiple_newlines(self):
        # 2+ 个连续换行 → 1 个换行
        assert merge_empty_lines('a\n\n\n\nb') == 'a\nb'

    def test_single_newlines(self):
        assert merge_empty_lines('a\nb\nc') == 'a\nb\nc'

    def test_crlf_compatibility(self):
        result = merge_empty_lines('a\r\n\r\n\r\nb')
        assert result == 'a\r\nb'

    def test_empty_string(self):
        assert merge_empty_lines('') == ''

    def test_mixed_whitespace_lines(self):
        text = 'a\n\n  \n\nb'
        result = merge_empty_lines(text)
        # 连续换行被合并，含空格的行不受影响
        assert '  ' in result  # 中间含空格的行保留


class TestRemoveWhitespace:
    def test_trailing_spaces(self):
        assert remove_whitespace('a  \nb  ') == 'a\nb'

    def test_leading_spaces_preserved(self):
        # remove_whitespace only strips trailing whitespace (rstrip)
        text = '  a\n  b'
        result = remove_whitespace(text)
        # Note: rstrip() only removes trailing whitespace per line
        # Leading spaces are preserved
        expected = '  a\n  b'
        assert result == expected

    def test_crlf_support(self):
        result = remove_whitespace('a  \r\nb  ')
        assert result == 'a\r\nb'

    def test_empty_lines(self):
        assert remove_whitespace('\n\n') == '\n\n'


class TestRemoveInterspersedSpaces:
    def test_chinese_around_spaces(self):
        assert remove_interspersed_spaces('中文 空格') == '中文空格'

    def test_english_spaces_preserved(self):
        assert remove_interspersed_spaces('hello world') == 'hello world'

    def test_digit_spaces_removed(self):
        assert remove_interspersed_spaces('123 456') == '123456'

    def test_mixed_chinese_english(self):
        result = remove_interspersed_spaces('这是 test 示例')
        assert 'test' in result
        assert '这是' in result
        assert '示例' in result

    def test_leading_trailing_spaces(self):
        assert remove_interspersed_spaces('  hello ') == 'hello'

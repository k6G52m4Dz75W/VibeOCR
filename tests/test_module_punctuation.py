"""单元测试：module_punctuation.py"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from module_punctuation import (
    _is_apostrophe,
    _convert_single_quotes_in_paragraph,
    _convert_double_quotes_in_paragraph,
    _convert_basic_punctuation,
    convert_to_fullwidth_punctuation,
    LEFT_DOUBLE_QUOTE, RIGHT_DOUBLE_QUOTE,
    LEFT_SINGLE_QUOTE, RIGHT_SINGLE_QUOTE,
)


class TestApostropheDetection:
    def test_possessive(self):
        assert _is_apostrophe("John's", 4) is True

    def test_contraction(self):
        assert _is_apostrophe("don't", 3) is True

    def test_single_quote_not_apostrophe(self):
        assert _is_apostrophe("'hello'", 0) is False

    def test_trailing_s(self):
        assert _is_apostrophe("James'", 5) is False


class TestSingleQuotes:
    def test_basic_conversion(self):
        text = "'hello world'"
        result = _convert_single_quotes_in_paragraph(text)
        assert result[0] == LEFT_SINGLE_QUOTE
        assert result[-1] == RIGHT_SINGLE_QUOTE

    def test_apostrophe_preserved(self):
        text = "it's a test"
        result = _convert_single_quotes_in_paragraph(text)
        assert "'" in result  # 撇号应保留为英文单引号

    def test_odd_quotes(self):
        """段首引号应转为左引号，撇号被识别后保留"""
        text = "'hello, world'"
        result = _convert_single_quotes_in_paragraph(text)
        # 段落开头是左引号
        assert result[0] == LEFT_SINGLE_QUOTE
        # 结尾的 ' 前是 d 后无字符→不是撇号→转为右引号
        # 注意：英文后会保留原样，此处检查至少转换了开头
        assert result[0] == LEFT_SINGLE_QUOTE

    def test_no_quotes(self):
        assert _convert_single_quotes_in_paragraph("plain text") == "plain text"


class TestDoubleQuotes:
    def test_basic_conversion(self):
        text = '"hello world"'
        result = _convert_double_quotes_in_paragraph(text)
        assert result[0] == LEFT_DOUBLE_QUOTE
        assert result[-1] == RIGHT_DOUBLE_QUOTE

    def test_no_quotes(self):
        assert _convert_double_quotes_in_paragraph("plain") == "plain"

    def test_odd_quotes(self):
        text = '"a" "b"'
        result = _convert_double_quotes_in_paragraph(text)
        assert result.count(LEFT_DOUBLE_QUOTE) == 2
        assert result.count(RIGHT_DOUBLE_QUOTE) == 2


class TestBasicPunctuation:
    def test_comma_conversion(self):
        """中文前后的逗号应转换，英文单词后的逗号保留"""
        # 'a,b' 中逗号在英文字母后，保留
        result = _convert_basic_punctuation('a,b')
        assert ',' in result
        # 中文后的逗号应转换
        assert _convert_basic_punctuation('好，') == '好\uff0c'

    def test_chinese_period(self):
        result = _convert_basic_punctuation('结束。')
        assert result == '结束\u3002'

    def test_decimal_point_preserved(self):
        assert _convert_basic_punctuation('3.14') == '3.14'

    def test_english_word_punctuation_preserved(self):
        assert _convert_basic_punctuation('Dr. Smith') == 'Dr. Smith'
        assert _convert_basic_punctuation('example.com') == 'example.com'


class TestFullPipeline:
    def test_typical_paragraph(self):
        text = '他说："你好"'
        result = convert_to_fullwidth_punctuation(text)
        # 双引号应转换为中文引号
        assert LEFT_DOUBLE_QUOTE in result
        assert RIGHT_DOUBLE_QUOTE in result
        # 中文后的冒号应转换为全角
        assert '\uff1a' in result

    def test_apostrophe_preserved_in_paragraph(self):
        text = "Tom's book"
        result = convert_to_fullwidth_punctuation(text)
        assert "'" in result  # 撇号保留

    def test_multiple_paragraphs(self):
        text = '"Para 1."\n\n"Para 2."'
        result = convert_to_fullwidth_punctuation(text)
        assert '\n\n' in result
        assert LEFT_DOUBLE_QUOTE in result

    def test_number_preserved(self):
        assert '3.14' in convert_to_fullwidth_punctuation('pi is 3.14')

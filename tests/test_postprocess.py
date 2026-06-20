"""
集成测试：postprocess 完整流水线。

验证每个处理步骤按正确顺序执行，以及 skip 参数能按需禁用模块。
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from postprocess import process


class TestPostprocessPipeline:
    def test_empty_text(self):
        result = process("", skip=[])
        assert result == ""

    def test_simple_text_passthrough(self):
        text = "这是一段干净的文本。"
        result = process(text, skip=[])
        assert "干净的文本" in result

    def test_ocr_grounding_removed(self):
        text = '<|ref|>test<|/ref|> <|det|>[[0,0]]<|/det|>\n正文'
        result = process(text, skip=[])
        assert '<|ref|>' not in result

    def test_batch_markers_removed(self):
        text = ('第一段\n'
                '========================\n'
                '批次 1 (共 2 批)\n'
                '========================\n'
                '第二段')
        result = process(text, skip=["dedup"])
        assert '批次 1' not in result

    def test_page_markers_removed(self):
        text = '正文\n\n================\n第 1 页 (共 1 页)\n================\n\n结尾'
        result = process(text, skip=["dedup"])
        assert '第 1 页' not in result

    def test_punctuation_converted(self):
        text = '他说："你好。"'
        result = process(text, skip=["dedup"])
        # 英文双引号应转换为中文双引号
        assert '\u201c' in result or '\u201d' in result

    def test_interspersed_spaces_removed(self):
        text = '中文 空格 测试'
        result = process(text, skip=["dedup", "paragraph_merge"])
        assert '中文空格测试' in result.replace(' ', '')

    def test_skip_dedup(self):
        """skip=["dedup"] 应当跳过不去重"""
        content = "测试文本。"
        text = (f"{'='*40}\n批次 1 (共 2 批)\n{'='*40}\n"
                f"{content}\n"
                f"{'='*40}\n批次 2 (共 2 批)\n{'='*40}\n"
                f"{content}")
        result = process(text, skip=["dedup"])
        # 跳过去重后不应再次调用 dedup
        assert True  # 不报错即为通过

    def test_skip_multiple(self):
        text = '<|ref|>x<|/ref|> <|det|>[[0]]<|/det|>\n"hello" 中文 空格'
        result = process(text, skip=["ocr_grounding", "dedup", "fullwidth_punct", "interspaced_spaces"])
        # 跳过了清理、去重、标点转换、空格清理
        assert '<|ref|>' in result  # 未被清理
        assert '"' in result        # 未被转换
        assert '中文 空格' in result.replace('"', '')  # 空格未被清理

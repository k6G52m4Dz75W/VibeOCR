"""单元测试：module_deduplication.py"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from module_deduplication import remove_overlap_duplicates


def make_batch_text(chunks):
    """辅助：将多个文本块拼成带批次标记的文本"""
    parts = []
    for i, chunk in enumerate(chunks):
        parts.append(f"{'='*40}\n批次 {i+1} (共 {len(chunks)} 批)\n{'='*40}\n")
        parts.append(chunk)
    return ''.join(parts)


class TestRemoveOverlapDuplicates:
    def test_no_overlap(self):
        chunks = [
            "第一段的内容在这里。",
            "第二段的内容完全不同。",
        ]
        text = make_batch_text(chunks)
        result = remove_overlap_duplicates(text)
        assert '第一段' in result
        assert '第二段' in result

    def test_simple_overlap(self):
        """相邻批次有 30 字符重叠时应去重"""
        # 重叠部分必须 >= 30 字符（OVERLAP_FINGERPRINT_LEN）
        overlap = "这是重叠的公共部分内容需要满三十个字才能被检测到。"
        chunks = [
            "第一段开头部分。" + overlap,
            overlap + "第二段后续内容部分。",
        ]
        text = make_batch_text(chunks)
        result = remove_overlap_duplicates(text)
        # 重叠部分只应出现一次（前一批次末尾被切除）
        # 注意：去重逻辑以 \n\n 拼接处置后的块，中间会多一个 \n\n
        assert overlap in result
        # 第一段的独有内容应该保留，第二段独有的也应该保留
        assert "第一段开头部分。" in result
        assert "第二段后续内容部分。" in result

    def test_identical_batches(self):
        """两批完全相同时应去重为一份"""
        content = "完全相同的文本内容。"
        chunks = [content, content]
        text = make_batch_text(chunks)
        result = remove_overlap_duplicates(text)
        # 拼接后应有且只有一份文本
        assert result.count(content) == 1

    def test_single_batch(self):
        """单批次不应报错"""
        text = make_batch_text(["只有一批的文本。"])
        result = remove_overlap_duplicates(text)
        assert '一批' in result

    def test_no_marker_text(self):
        """无批次标记的文本原样返回"""
        text = "没有批次标记的普通文本。"
        result = remove_overlap_duplicates(text)
        assert result == text

    def test_empty_text(self):
        """空文本应返回空"""
        result = remove_overlap_duplicates("")
        assert result == ""

# postprocess.py
import module_cleaning as cleaning
import module_punctuation as punctuation
import module_heuristic_merge as heuristic_merge
import module_deduplication as deduplication


def process(text, skip=None):
    """
    统一后处理入口

    参数:
        text: 输入文本（长字符串，可以是多批次合并内容）
        skip: 可选，要跳过的处理模块名称列表
              支持: "ocr_grounding", "dedup", "batch_markers", "page_markers",
                    "empty_lines", "whitespace", "paragraph_merge",
                    "fullwidth_punct", "interspaced_spaces"
              示例: process(text, skip=["dedup"]) 跳过去重步骤
    """
    if skip is None:
        skip = []

    # 清除DeepSeek-OCR输出中的定位标签
    if "ocr_grounding" not in skip:
        text = cleaning.remove_ocr_grounding(text)

    # 【批次去重】基于批次标记拆分，必须在 remove_batch_markers 之前
    if "dedup" not in skip:
        text = deduplication.remove_overlap_duplicates(text)

    # 清除批次标记 (===批次n (共m批)===)
    if "batch_markers" not in skip:
        text = cleaning.remove_batch_markers(text)

    # 兼容旧格式：清除页标记
    if "page_markers" not in skip:
        text = cleaning.remove_page_markers(text)

    # 合并多余空行
    if "empty_lines" not in skip:
        text = cleaning.merge_empty_lines(text)

    # 清理空白
    if "whitespace" not in skip:
        text = cleaning.remove_whitespace(text)

    # 启发式合并断行段落
    if "paragraph_merge" not in skip:
        text = heuristic_merge.heuristic_paragraph_merge(text)

    # 英文标点转中文全角标点
    if "fullwidth_punct" not in skip:
        text = punctuation.convert_to_fullwidth_punctuation(text)

    # 清理中文夹杂空格
    if "interspaced_spaces" not in skip:
        text = cleaning.remove_interspersed_spaces(text)

    return text
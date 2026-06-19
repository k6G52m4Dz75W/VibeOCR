# postprocess.py
import cleaning
import punctuation
import heuristic_merge

def process(text):
    """
    统一后处理入口 (批次版，无去重)
    输入: 长字符串（已合并的所有批次内容）
    """
    # 清除DeepSeek-OCR输出中的定位标签
    text = cleaning.remove_ocr_grounding(text)

    # 清除批次标记 (===批次n (共m批)===)
    text = cleaning.remove_batch_markers(text)

    # 兼容旧格式：清除页标记
    text = cleaning.remove_page_markers(text)

    # 合并多余空行
    text = cleaning.merge_empty_lines(text)

    # 清理空白
    text = cleaning.remove_whitespace(text)
 
    # 启发式合并断行段落
    text = heuristic_merge.heuristic_paragraph_merge(text)

    # 英文标点转中文全角标点
    text = punctuation.convert_to_fullwidth_punctuation(text)

    # 清理中文夹杂空格
    text = cleaning.remove_interspersed_spaces(text)

    return text
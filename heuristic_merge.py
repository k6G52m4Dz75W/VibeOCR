# heuristic_merge.py
import re

# 定义结束标点符号的集合（包含中文和英文）
END_PUNCTUATION = {
    '。', '！', '？', '；', '…',  # 常见中文结束标点
    '.', '!', '?', ';',        # 常见英文结束标点
    '”', '’', '"',              # 引号
    '》', ']', ')'              # 闭合括号
}

def is_chinese_char(char):
    """判断单个字符是否为中文字符"""
    return '\u4e00' <= char <= '\u9fff'

def heuristic_paragraph_merge(text):
    """
    启发式段落合并 (终极修复版 - 解决中文多余空格问题)
    """
    print("🔧 启发式合并段落：正在修复意外断行...")
    
    lines = text.splitlines()
    result_lines = []
    
    for i, line in enumerate(lines):
        line = line.strip()
        # 如果是最后一行，直接加入结果
        if i == len(lines) - 1:
            result_lines.append(line)
            break
            
        next_line = lines[i + 1].strip()
        
        # 判断当前行是否为空
        if not line:
            continue
            
        last_char = line[-1] if line else ''
        
        # --- 核心逻辑 ---
        is_end_with_punctuation = last_char in END_PUNCTUATION
        is_short_line = len(line) <= 10 
        
        # 只有在“不以标点结尾”并且“不是短行”的情况下，才执行合并
        if not is_end_with_punctuation and not is_short_line:
            # 【修复】智能判断是否需要加空格
            # 获取下一行的第一个字符（防止越界）
            first_char_next = next_line[0] if next_line else ''
            
            # 如果当前行末尾或下一行开头是中文字符，则不加空格直接拼接
            if is_chinese_char(last_char) or is_chinese_char(first_char_next):
                lines[i + 1] = line + next_line
            else:
                # 纯英文或数字等情况，保留原有的加空格逻辑
                lines[i + 1] = line + ' ' + next_line
                
            print(f"   合并断行: '{line[:10]}...' -> '{next_line[:10]}...'")
        else:
            # 如果是以标点结尾，或者是短行（标题/序号），则保留当前行
            result_lines.append(line)
    
    merged_text = '\n'.join(result_lines)
    merged_text = re.sub(r' {2,}', ' ', merged_text)
    
    print(f"✅ 启发式合并完成。")
    return merged_text
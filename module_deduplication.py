# deduplication.py
import re

def remove_overlap_duplicates(text):
    """
    基于批次拆分的精准去重 (终极重构版)
    逻辑：1. 按分割线拆分全文本为独立数组；2. 逐块修剪上一块的尾巴；3. 重新拼接并清理分割线
    """
    OVERLAP_FINGERPRINT_LEN = 30  # 指纹长度
    # 匹配批次分割线的正则表达式
    BATCH_MARKER_PATTERN = re.compile(r'=+\s*批次\s*\d+\s*\(共\s*\d+\s*批\)\s*=+')
    
    print(f"【批次拆分去重启动】指纹长度={OVERLAP_FINGERPRINT_LEN}")

    # 2. 【核心步骤一】利用分割线将全文本拆解为独立的批次文本块数组
    raw_chunks = re.split(BATCH_MARKER_PATTERN, text)
    # 过滤掉空字符串，得到纯净的批次文本块列表
    batch_chunks = [chunk.strip() for chunk in raw_chunks if chunk.strip()]
    print(f"✅ 成功将文本拆分为 {len(batch_chunks)} 个独立批次块")

    # 3. 【核心步骤二】逐块比对与修剪
    # 从第2个批次块（索引为1）开始遍历
    for i in range(1, len(batch_chunks)):
        current_chunk = batch_chunks[i]
        prev_chunk = batch_chunks[i - 1]
        
        # 提取当前批次开头的指纹
        fingerprint = current_chunk[:OVERLAP_FINGERPRINT_LEN]
        print(f"\n🔍 正在处理批次 {i+1}...")
        print(f" 提取的指纹: '{fingerprint}'")
        
        if not fingerprint:
            continue
            
        # 在上一批次中搜索这个指纹
        overlap_pos = prev_chunk.find(fingerprint)

    # 如果显示 '...\r\n\r\n...' 说明是 \r\n 问题
        if overlap_pos != -1:
            print(f" ✅ 在上一批次中找到重叠位置: {overlap_pos}")
            # 切除上一批次从这个位置开始直到结束的所有文本
            batch_chunks[i - 1] = prev_chunk[:overlap_pos]
            print(f" 🗑️ 已切除上一批次末尾的重叠部分")
        else:
            print(f" ❌ 未在上一批次中找到该指纹")

    # 4. 【核心步骤三】将修剪好的文本块首尾拼接成完整文本
    final_text = "\n\n".join(batch_chunks)

    # --- 恢复数量统计 ---
    # 计算去重后的段落数（基于换行符分割）
    cleaned_blocks = [block.strip() for block in final_text.split('\n\n') if block.strip()]
    final_count = len(cleaned_blocks)
    # original_count = len(text_blocks)
    
    print(f"\n✅ 批次拆分去重完成。")
    # print(f"   段落统计: 原始 {original_count} -> 剩余 {final_count}")
    
    return final_text  # <--- 直接返回字符串
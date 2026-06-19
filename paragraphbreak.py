import json

def insert_br_for_large_paragraph_gaps(json_data):
    """
    遍历 PaddleOCR-VL 的 block 物理间距。
    只有当两个 block 之间的垂直间距明显大于常规段落间距时，才在之前加入 <br />
    """
    # 1. 提取单页内的所有 block 列表
    page_data = json_data[0] if isinstance(json_data, list) else json_data
    res_list = page_data.get("prunedResult", {}).get("parsing_res_list", [])
    
    if not res_list:
        return ""
    
    # 2. 过滤掉不要的、或者不含坐标的干扰标签，保证按纵坐标(ymin)从上到下严格排序
    valid_blocks = []
    for block in res_list:
        label = block.get("block_label")
        if label not in ["number", "footer", "header"] and "block_bbox" in block:
            valid_blocks.append(block)
            
    valid_blocks.sort(key=lambda b: b["block_bbox"][1])
    
    if not valid_blocks:
        return ""
        
    # 3. 第一步：先找出整张页面上段落之间最普遍、最常规的“相邻基础间距”是多少
    gaps = []
    for i in range(1, len(valid_blocks)):
        prev_box = valid_blocks[i - 1]["block_bbox"]
        curr_box = valid_blocks[i]["block_bbox"]
        # delta_y = 下一个块的顶(ymin) - 上一个块的底(ymax)
        delta_y = curr_box[1] - prev_box[3]
        if delta_y > 0:
            gaps.append(delta_y)
            
    # 如果没法计算间距，直接把内容按原顺序拼起来
    if not gaps:
        return "\n".join([b.get("block_content", "").strip() for b in valid_blocks])
        
    # 计算常规段落间距的均值或中位数作为“基本线”
    # 例如正文段落之间一般只空 10 像素左右
    base_gap = sorted(gaps)[len(gaps) // 2]
    
    # 4. 第二步：正式遍历并构建文本。如果当前段落与上一段的距离比常规间距明显宽大（比如大 3 倍以上），就插入 <br />
    final_output = valid_blocks[0].get("block_content", "").strip()
    
    for i in range(1, len(valid_blocks)):
        prev_box = valid_blocks[i - 1]["block_bbox"]
        curr_box = valid_blocks[i]["block_bbox"]
        curr_text = valid_blocks[i].get("block_content", "").strip()
        
        if not curr_text:
            continue
            
        delta_y = curr_box[1] - prev_box[3]
        
        # 判断：如果两块之间的物理空隙达到了常规间距的 3.5 倍以上，说明这里是个巨大的空行
        if delta_y > (base_gap * 3.5):
            # 在该行之前插入 <br /> 并追加文本
            final_output += f"\n<br />\n{curr_text}"
        else:
            # 属于正常相邻段落，直接还原常规换行连接
            final_output += f"\n{curr_text}"
            
    return final_output

# ==================== 测试运行 ====================
if __name__ == "__main__":
    file_path = "chapter10cropped2.pdf_by_PaddleOCR-VL-1.6.json"
    
    with open(file_path, "r", encoding="utf-8") as f:
        ocr_data = json.load(f)
        
    # 获取转换后仅在大空行处带 <br /> 的最终文本
    output_text = insert_br_for_large_paragraph_gaps(ocr_data)
    print(output_text)
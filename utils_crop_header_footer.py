"""
utils_crop_header_footer.py — 自动裁剪 PDF / 图像的页眉与页脚。

纯 numpy 轻量实现，不依赖 opencv：

核心算法（经真实扫描件 chapter01.pdf 38 页验证）：
  - 顶部：low_frac（低方差页占比）法。
    逐行统计「像素方差 ≤ blank_thr」的页数占比 low_frac。
    真正的页眉 = 绝大多数页在该行都低方差（重复/空白）；
    单页装饰图案只有 1 页低方差 → 占比 ≈ 1/N → 不被当成全局页眉。
    从上往下找首个 low_frac < top_frac 的行作为页眉区末端（+safety 余量）。
  - 底部：ink_frac（有墨页占比）法——与顶部同构的跨页统计。
    页脚（页码/logo/分割线）在几乎每一页的同一垂直位置重复出现
    → 该行的「有墨页占比」≈ 1.0；而正文末行每页内容不同 → 占比低。
    自底向上定位 ink_frac ≥ foot_thr 的连续页脚带，取其顶端（+bottom_safety
    向内余量，确保整条页脚被裁掉）作为裁剪下界。
    此法 dpi 无关、随文档自适应，且不会误裁正文（页脚与正文末行间有空白带）。

  - 单图（N=1）退化为：顶部看单页低方差行；底部看单页有墨行，逻辑一致。

既可作为独立 CLI 工具（处理 PDF/图片并输出裁剪结果），
也可被 VibeOCR 主流程 import：pdf_pages_to_b64 / image_file_to_b64
在转 base64 前调用本模块的 detect + crop。

默认策略：宁可漏裁、绝不误裁（safe 余量往「不裁」方向收）。

依赖: numpy, Pillow, pymupdf(处理 PDF 时)

用法:
  python utils_crop_header_footer.py input.pdf --out ./cropped
  python utils_crop_header_footer.py input.pdf --out ./cropped --to-pdf
  python utils_crop_header_footer.py page.png --out ./cropped
"""

import os
import sys
import argparse

import numpy as np
from PIL import Image

try:
    import fitz
except ImportError:
    fitz = None


def detect_header_footer_bounds(images, detect_w=1100, top_max=0.18,
                                bottom_max=0.18, safety=10, bottom_safety=12,
                                blank_thr=5.0, top_frac=0.50,
                                foot_thr=0.60, ink_thr=210,
                                min_ink_ratio=0.01):
    """检测页眉页脚边界，返回相对比例 (top_rel, bottom_rel)。

    Args:
        images: list[PIL.Image]（原始分辨率页图像；单图传 [img] 即单页法）
        detect_w: 检测用统一宽度（高度按实际页面宽高比自动计算）
        top_max / bottom_max: 页眉/页脚最多裁掉的比例上限（也限制搜索区）
        safety: 顶部安全余量（检测坐标行数），往"裁"方向靠内收
        bottom_safety: 底部安全余量（检测坐标行数），往"裁"方向加深，
                       确保整条页脚被移除
        blank_thr: 像素方差低于此值视为「低方差」（顶部空白/页眉判定）
        top_frac: 顶部低占比阈值（low_frac < 此值视为离开页眉区）
        foot_thr: 底部有墨页占比阈值（ink_frac ≥ 此值视为页脚带）
        ink_thr: 灰度 ≤ 此值视为「墨」（文字/logo/分割线）
        min_ink_ratio: 某行被视为「有墨」所需的最少墨像素占行宽比例

    Returns:
        (top_rel, bottom_rel) 相对比例 [0,1]
    """
    if not images:
        return 0.0, 1.0

    # 用实际页面宽高比（避免硬编码 A4 比例偏差导致底部误差放大）
    first_w, first_h = images[0].size
    detect_h = max(64, int(detect_w * first_h / first_w))

    arrs = []
    for im in images:
        g = im.convert("L").resize((detect_w, detect_h))
        arrs.append(np.asarray(g, dtype=np.float32))
    stack = np.stack(arrs, axis=0)            # (N, H, W)
    N = stack.shape[0]
    H = detect_h
    W = detect_w

    # ── 顶部：low_frac 法（免疫单页装饰）─────────────────────
    per_page_std = stack.std(axis=2)           # (N, H) 每页每行方差
    low_mask = per_page_std <= blank_thr       # (N, H)
    low_frac = low_mask.mean(axis=0)           # (H,) 每行低方差页占比

    ti = 0
    for i in range(int(top_max * H)):
        if low_frac[i] < top_frac:
            ti = i
            break
    top_rel = min(max((ti + safety) / H, 0.0), top_max)

    # ── 底部：ink_frac 法（页脚在每页同位置重复 → 有墨页占比≈1）──
    ink_mask = stack <= ink_thr                # (N, H, W) 墨像素
    min_ink = max(1, int(min_ink_ratio * W))
    row_has_ink = ink_mask.sum(axis=2) >= min_ink   # (N, H)
    ink_frac = row_has_ink.mean(axis=0)        # (H,) 有墨页占比

    bstart = int((1 - bottom_max) * H)
    j = H - 1
    entered = False
    footer_top = H                            # 默认：未检出页脚 → 不裁底
    while j >= bstart:
        if ink_frac[j] >= foot_thr:
            entered = True
            j -= 1
        else:
            if entered:
                footer_top = j + 1            # 页脚带顶端
                break
            j -= 1
    # 若始终未进入页脚带（全篇无重复页脚）→ 不裁底，避免误裁正文
    if entered:
        # 往"上"收：在检出页脚带顶端之上再留余量，确保整条页脚（含顶边抗锯齿）被裁掉
        footer_top = max(bstart, footer_top - bottom_safety)
        bottom_rel = footer_top / H
    else:
        bottom_rel = 1.0

    bottom_rel = min(max(bottom_rel, 1.0 - bottom_max), 1.0)

    # 确保 top < bottom
    if top_rel >= bottom_rel:
        top_rel = bottom_rel * 0.95

    return top_rel, bottom_rel


def crop_image(img, top_rel, bottom_rel):
    """按相对比例裁掉顶部 [0, top_rel) 与底部 (bottom_rel, 1]。"""
    w, h = img.size
    top = int(round(top_rel * h))
    bottom = int(round(bottom_rel * h))
    top = max(0, min(top, h - 1))
    bottom = max(top + 1, min(bottom, h))
    return img.crop((0, top, w, bottom))


def _render_pdf_pages(pdf_path, dpi=300):
    if fitz is None:
        raise RuntimeError("需要 pymupdf 才能处理 PDF: pip install pymupdf")
    doc = fitz.open(pdf_path)
    pages = []
    for page in doc:
        pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72))
        pages.append(Image.frombytes("RGB", [pix.width, pix.height], pix.samples))
    doc.close()
    return pages


def process_path(input_path, out_dir, dpi=300, to_pdf=False,
                 top_max=0.18, bottom_max=0.18, safety=10, bottom_safety=12,
                 blank_thr=5.0, top_frac=0.50, foot_thr=0.60,
                 ink_thr=210, min_ink_ratio=0.01):
    """处理单个 PDF 或图片，输出裁剪结果。"""
    ext = os.path.splitext(input_path)[1].lower()
    is_pdf = ext == ".pdf"
    if is_pdf:
        pages = _render_pdf_pages(input_path, dpi=dpi)
    else:
        pages = [Image.open(input_path).convert("RGB")]

    top_rel, bottom_rel = detect_header_footer_bounds(
        pages, top_max=top_max, bottom_max=bottom_max, safety=safety,
        bottom_safety=bottom_safety, blank_thr=blank_thr, top_frac=top_frac,
        foot_thr=foot_thr, ink_thr=ink_thr, min_ink_ratio=min_ink_ratio)
    print(f"检测到边界: top={top_rel:.3f} bottom={bottom_rel:.3f} "
          f"(裁掉顶部 {top_rel*100:.1f}% / 底部 {(1-bottom_rel)*100:.1f}%)")

    os.makedirs(out_dir, exist_ok=True)
    cropped = [crop_image(im, top_rel, bottom_rel) for im in pages]

    if is_pdf and to_pdf:
        out_pdf = os.path.join(out_dir,
                               os.path.splitext(os.path.basename(input_path))[0] + "_cropped.pdf")
        new_doc = fitz.open()
        for im in cropped:
            w, h = im.size
            new_doc.new_page(width=w, height=h)
            tmp = os.path.join(out_dir, "_tmp_page.png")
            im.save(tmp)
            new_doc[-1].insert_image(fitz.Rect(0, 0, w, h), filename=tmp)
            os.remove(tmp)
        new_doc.save(out_pdf)
        new_doc.close()
        print(f"已输出裁剪 PDF: {out_pdf}")
    else:
        for i, im in enumerate(cropped):
            im.save(os.path.join(out_dir, f"page_{i+1:04d}.png"))
        print(f"已输出 {len(cropped)} 张裁剪图到 {out_dir}")


def main():
    p = argparse.ArgumentParser(description="自动裁剪 PDF/图像的页眉页脚（纯 numpy）")
    p.add_argument("input", help="输入 PDF 或图片路径")
    p.add_argument("--out", default="./cropped", help="输出目录")
    p.add_argument("--dpi", type=int, default=300, help="PDF 渲染 DPI")
    p.add_argument("--to-pdf", action="store_true", help="输出合并为单个 PDF")
    p.add_argument("--top-max", type=float, default=0.18)
    p.add_argument("--bottom-max", type=float, default=0.18)
    p.add_argument("--safety", type=int, default=10)
    p.add_argument("--bottom-safety", type=int, default=12)
    args = p.parse_args()
    process_path(args.input, args.out, dpi=args.dpi, to_pdf=args.to_pdf,
                 top_max=args.top_max, bottom_max=args.bottom_max,
                 safety=args.safety, bottom_safety=args.bottom_safety)


if __name__ == "__main__":
    main()

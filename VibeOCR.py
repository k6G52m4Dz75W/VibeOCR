import sys
import os
import time
import json
import zipfile
import tempfile
import requests
from typing import Any

try:
    import version
    __version__ = version.VERSION
except ImportError:
    __version__ = "0.0.0"

try:
    import postprocess
except ImportError:
    print("请将 postprocess.py 放在同一目录下")
    sys.exit(1)

try:
    from llm_ocr import (
        load_model_config,
        pdf_pages_to_b64,
    pdf_pages_to_pdf_b64,
        build_payload,
        build_headers,
        ocr_batch,
        OPENAI_AVAILABLE,
        DEFAULT_MODEL,
        CONFIGS,
    )
except ImportError:
    print("请将 llm_ocr.py 放在同一目录下")
    sys.exit(1)


# ===================== PaddleOCR-VL-1.6 异步任务支持 =====================

def paddleocr_submit_job(config: dict[str, Any], file_path: str, max_retries: int = 3, retry_delay: int = 5) -> str:
    """提交 PaddleOCR-VL-1.6 异步任务，返回 jobId"""
    job_url = config["api_url"]
    token = config["api_key"]
    model = config["model_id"]
    optional_payload = config.get("payload_template", {})

    headers = {
        "Authorization": f"bearer {token}",
    }

    print(f"📤 提交任务: {file_path}")

    last_error = None
    for attempt in range(1, max_retries + 1):
        print(f"  发送请求 (尝试 {attempt}/{max_retries})...", end=" ")
        try:
            if file_path.startswith("http"):
                # URL Mode
                headers["Content-Type"] = "application/json"
                payload = {
                    "fileUrl": file_path,
                    "model": model,
                    "optionalPayload": optional_payload
                }
                job_response = requests.post(job_url, json=payload, headers=headers, timeout=config.get("timeout", 30))
            else:
                # Local File Mode
                if not os.path.exists(file_path):
                    raise FileNotFoundError(f"文件不存在: {file_path}")

                data = {
                    "model": model,
                    "optionalPayload": json.dumps(optional_payload)
                }
                with open(file_path, "rb") as f:
                    files = {"file": f}
                    job_response = requests.post(job_url, headers=headers, data=data, files=files, timeout=config.get("timeout", 30))

            # 检查 HTTP 状态码，非 200 时输出响应体辅助排查
            if job_response.status_code != 200:
                print(f"  ⚠️  HTTP {job_response.status_code}: {job_response.text[:500]}")
            job_response.raise_for_status()
            resp_data = job_response.json()
            job_id = resp_data["data"]["jobId"]
            print(f"✅ 任务已提交, jobId: {job_id}")
            return job_id

        except Exception as e:
            last_error = e
            print(f"❌ 失败: {e}")
            if attempt < max_retries:
                print(f"  ⏳ {retry_delay}秒后重试...")
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                print("  💥 已达到最大重试次数，放弃")

    raise last_error


def paddleocr_poll_job(config: dict[str, Any], job_id: str, poll_interval: int = 5) -> str:
    """轮询 PaddleOCR-VL-1.6 任务状态，完成后返回 jsonl_url"""
    job_url = config["api_url"]
    token = config["api_key"]

    headers = {
        "Authorization": f"bearer {token}",
    }

    print(f"🔍 开始轮询任务状态 (jobId: {job_id})...")
    jsonl_url = ""

    while True:
        try:
            job_result_response = requests.get(f"{job_url}/{job_id}", headers=headers, timeout=30)
            job_result_response.raise_for_status()
            data = job_result_response.json()["data"]
            state = data["state"]

            if state == 'pending':
                print("  ⏳ 任务状态: pending")
            elif state == 'running':
                try:
                    total_pages = data['extractProgress']['totalPages']
                    extracted_pages = data['extractProgress']['extractedPages']
                    print(f"  🏃 任务状态: running, 总页数: {total_pages}, 已提取: {extracted_pages}")
                except KeyError:
                    print("  🏃 任务状态: running...")
            elif state == 'done':
                extracted_pages = data['extractProgress']['extractedPages']
                start_time = data['extractProgress']['startTime']
                end_time = data['extractProgress']['endTime']
                print(f"  ✅ 任务完成! 成功提取页数: {extracted_pages}, 开始: {start_time}, 结束: {end_time}")
                jsonl_url = data['resultUrl']['jsonUrl']
                break
            elif state == "failed":
                error_msg = data.get('errorMsg', '未知错误')
                print(f"  ❌ 任务失败: {error_msg}")
                raise RuntimeError(f"PaddleOCR-VL 任务失败: {error_msg}")

        except requests.exceptions.RequestException as e:
            print(f"  ⚠️  轮询请求异常: {e}, 继续轮询...")

        time.sleep(poll_interval)

    return jsonl_url


def paddleocr_fetch_results(jsonl_url: str) -> tuple[list[str], list[dict[str, Any]]]:
    """下载并解析 jsonl 结果，返回 (markdown文本列表, 原始json数据列表)"""
    print(f"📥 下载结果: {jsonl_url}")
    jsonl_response = requests.get(jsonl_url, timeout=60)
    jsonl_response.raise_for_status()

    lines = jsonl_response.text.strip().split('\n')
    all_texts = []
    all_json_data = []  # 新增：保存完整的结构化数据
    page_num = 0

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)  # 保留完整解析结果
            result = parsed["result"]

            # 构建每页的结构化数据
            page_data = {
                "page_index": page_num,
                "result": result  # 保存完整的 result 结构
            }
            all_json_data.append(page_data)

            for res in result["layoutParsingResults"]:
                md_text = res["markdown"]["text"]
                all_texts.append(md_text)
                page_num += 1

        except (json.JSONDecodeError, KeyError) as e:
            print(f"  ⚠️  解析结果行失败: {e}")
            continue

    print(f"✅ 共解析 {len(all_texts)} 页结果")
    return all_texts, all_json_data


# ===================== PaddleOCR 异步任务通用支持 (VL-1.6 / v6) =====================

def paddleocr_v6_fetch_results(jsonl_url: str) -> tuple[list[str], list[dict[str, Any]]]:
    """下载并解析 PP-OCRv6 jsonl 结果，返回 (文本列表, 原始json数据列表)
    
    PP-OCRv6 结果与 PaddleOCR-VL 使用相同 jsonl 格式，但字段结构不同：
    - PP-OCRv6: result.ocrResults[].prunedResult.rec_texts (每页一个行文本数组)
    - PaddleOCR-VL: result.layoutParsingResults[].markdown.text
    """
    print(f"📥 下载结果: {jsonl_url}")
    jsonl_response = requests.get(jsonl_url, timeout=60)
    jsonl_response.raise_for_status()

    lines = jsonl_response.text.strip().split('\n')
    all_texts = []
    all_json_data = []
    page_num = 0

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
            result = parsed["result"]

            # 构建每页的结构化数据（含完整的 result 原始数据 + 页面索引）
            page_data = {
                "page_index": page_num,
                "result": result
            }
            all_json_data.append(page_data)

            # 解析 PP-OCRv6 的 ocrResults 结构
            # 实际返回: result.ocrResults[].prunedResult.rec_texts (每行一条字符串)
            ocr_results = result.get("ocrResults", [])
            for res in ocr_results:
                pruned = res.get("prunedResult", {})
                rec_texts = pruned.get("rec_texts", [])
                text = "\n".join(t for t in rec_texts if isinstance(t, str))
                if text.strip():
                    all_texts.append(text)
                page_num += 1

        except (json.JSONDecodeError, KeyError) as e:
            print(f"  ⚠️  解析结果行失败: {e}")
            continue

    print(f"✅ 共解析 {len(all_texts)} 条 OCR 结果")
    return all_texts, all_json_data


def run_paddleocr_async(config: dict[str, Any], file_path: str) -> tuple[list[str], list[dict[str, Any]]]:
    """PaddleOCR 异步任务通用流程（VL / v6 共用）：提交 -> 轮询 -> 获取结果
    根据 config.content_format 自动选择解析方式"""
    job_id = paddleocr_submit_job(config, file_path)
    jsonl_url = paddleocr_poll_job(config, job_id)
    if config["content_format"] == "pp-ocrv6":
        return paddleocr_v6_fetch_results(jsonl_url)
    return paddleocr_fetch_results(jsonl_url)


# ===================== MinerU Precision Extract API (v4) 支持 =====================

def mineru_get_upload_url(config: dict[str, Any], file_path: str, max_retries: int = 3, retry_delay: int = 5) -> tuple[str, str]:
    """申请 MinerU 文件上传 URL，返回 (batch_id, upload_url)"""
    base_url = config["api_url"]
    token = config["api_key"]
    template = config.get("payload_template", {})

    file_name = os.path.basename(file_path)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

    data = {
        "files": [
            {
                "name": file_name,
                "is_ocr": template.get("is_ocr", True),
            }
        ],
        "model_version": template.get("model_version", "vlm"),
        "enable_formula": template.get("enable_formula", True),
        "enable_table": template.get("enable_table", True),
        "language": template.get("language", "ch"),
    }

    # 可选参数
    if template.get("extra_formats"):
        data["extra_formats"] = template["extra_formats"]
    if template.get("page_ranges"):
        data["files"][0]["page_ranges"] = template["page_ranges"]

    url = f"{base_url}/file-urls/batch"

    last_error = None
    for attempt in range(1, max_retries + 1):
        print(f"  申请上传URL (尝试 {attempt}/{max_retries})...", end=" ")
        try:
            resp = requests.post(url, headers=headers, json=data, timeout=config.get("timeout", 30))
            resp.raise_for_status()
            result = resp.json()

            if result.get("code") != 0:
                raise RuntimeError(f"MinerU API 错误: {result.get('msg', '未知错误')}")

            batch_id = result["data"]["batch_id"]
            upload_urls = result["data"]["file_urls"]
            upload_url = upload_urls[0] if upload_urls else None

            if not upload_url:
                raise RuntimeError("未获取到上传URL")

            print(f"✅ batch_id: {batch_id}")
            return batch_id, upload_url

        except Exception as e:
            last_error = e
            print(f"❌ 失败: {e}")
            if attempt < max_retries:
                print(f"  ⏳ {retry_delay}秒后重试...")
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                print("  💥 已达到最大重试次数，放弃")

    raise last_error


def mineru_upload_file(upload_url: str, file_path: str, max_retries: int = 3, retry_delay: int = 5) -> bool:
    """PUT 上传文件到 MinerU 的 signed URL"""
    print(f"📤 上传文件到 MinerU...")

    last_error = None
    for attempt in range(1, max_retries + 1):
        print(f"  PUT上传 (尝试 {attempt}/{max_retries})...", end=" ")
        try:
            with open(file_path, "rb") as f:
                resp = requests.put(upload_url, data=f, timeout=120)
                resp.raise_for_status()
            print("✅ 上传成功")
            return True
        except Exception as e:
            last_error = e
            print(f"❌ 失败: {e}")
            if attempt < max_retries:
                print(f"  ⏳ {retry_delay}秒后重试...")
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                print("  💥 已达到最大重试次数，放弃")

    raise last_error


def mineru_poll_batch(config: dict[str, Any], batch_id: str, poll_interval: int = 5, timeout: int = 600) -> str:
    """轮询 MinerU batch 任务状态，完成后返回 full_zip_url"""
    base_url = config["api_url"]
    token = config["api_key"]

    headers = {
        "Authorization": f"Bearer {token}"
    }

    url = f"{base_url}/extract-results/batch/{batch_id}"

    print(f"🔍 开始轮询 MinerU 任务状态 (batch_id: {batch_id})...")
    start_time = time.time()

    while True:
        elapsed = int(time.time() - start_time)
        if elapsed > timeout:
            raise TimeoutError(f"轮询超时 ({timeout}秒)，请手动查询 batch_id: {batch_id}")

        try:
            resp = requests.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
            result = resp.json()

            if result.get("code") != 0:
                raise RuntimeError(f"MinerU API 错误: {result.get('msg', '未知错误')}")

            extract_results = result["data"]["extract_result"]
            if not extract_results:
                print(f"  ⏳ [{elapsed}s] 等待结果...")
                time.sleep(poll_interval)
                continue

            # 只处理第一个文件（单文件模式）
            task = extract_results[0]
            state = task["state"]
            file_name = task.get("file_name", "unknown")

            if state == "waiting-file":
                print(f"  ⏳ [{elapsed}s] 等待文件上传...")
            elif state == "pending":
                print(f"  ⏳ [{elapsed}s] 排队中...")
            elif state == "running":
                try:
                    total = task["extract_progress"]["total_pages"]
                    extracted = task["extract_progress"]["extracted_pages"]
                    print(f"  🏃 [{elapsed}s] 提取中... {extracted}/{total} 页")
                except KeyError:
                    print(f"  🏃 [{elapsed}s] 提取中...")
            elif state == "converting":
                print(f"  🔧 [{elapsed}s] 格式转换中...")
            elif state == "done":
                full_zip_url = task["full_zip_url"]
                print(f"  ✅ [{elapsed}s] 任务完成!")
                return full_zip_url
            elif state == "failed":
                err_msg = task.get("err_msg", "未知错误")
                print(f"  ❌ [{elapsed}s] 任务失败: {err_msg}")
                raise RuntimeError(f"MinerU 提取失败: {err_msg}")
            else:
                print(f"  ❓ [{elapsed}s] 未知状态: {state}")

        except requests.exceptions.RequestException as e:
            print(f"  ⚠️  [{elapsed}s] 轮询请求异常: {e}, 继续轮询...")

        time.sleep(poll_interval)


def mineru_download_and_extract(zip_url: str) -> tuple[str, dict[str, Any]]:
    """下载 zip 并提取 full.md 内容和结构化 json 数据"""
    print(f"📥 下载结果 zip: {zip_url}")

    resp = requests.get(zip_url, timeout=120)
    resp.raise_for_status()

    md_content = ""
    json_data = {}

    # 使用 TemporaryDirectory 自动清理，无需手动 os.unlink
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = os.path.join(tmp_dir, "result.zip")
        with open(tmp_path, "wb") as tmp:
            tmp.write(resp.content)

        with zipfile.ZipFile(tmp_path, 'r') as zf:
            # 查找 full.md
            md_file = None
            for name in zf.namelist():
                if name.endswith("full.md") or name == "full.md":
                    md_file = name
                    break

            if not md_file:
                # 尝试找任何 .md 文件
                md_files = [n for n in zf.namelist() if n.endswith(".md")]
                if md_files:
                    md_file = md_files[0]
                else:
                    raise FileNotFoundError("zip 中未找到 markdown 文件")

            print(f"  📄 提取: {md_file}")
            with zf.open(md_file) as f:
                md_content = f.read().decode('utf-8')

            # 查找 json 文件（结构化数据）
            json_file = None
            for name in zf.namelist():
                if name.endswith(".json") and ("content" in name or "structure" in name or "middle" in name):
                    json_file = name
                    break
            
            # 如果没找到特定 json，找任意 json
            if not json_file:
                json_files = [n for n in zf.namelist() if n.endswith(".json")]
                if json_files:
                    json_file = json_files[0]

            if json_file:
                print(f"  📄 提取: {json_file}")
                with zf.open(json_file) as f:
                    json_data = json.loads(f.read().decode('utf-8'))
            else:
                print("  ⚠️  zip 中未找到 json 文件")

        print(f"✅ 提取完成，md 共 {len(md_content)} 字符")
        return md_content, json_data


def mineru_ocr(config: dict[str, Any], file_path: str) -> tuple[list[str], list[dict[str, Any]]]:
    """MinerU 完整流程：申请URL -> 上传文件 -> 轮询 -> 下载zip -> 提取md和json"""
    batch_id, upload_url = mineru_get_upload_url(config, file_path)
    mineru_upload_file(upload_url, file_path)
    zip_url = mineru_poll_batch(config, batch_id)
    content, json_data = mineru_download_and_extract(zip_url)
    # 返回格式与 paddleocr_ocr 一致: (文本列表, json数据列表)
    all_json_data = [{"page_index": 0, "result": json_data}] if json_data else []
    return [content], all_json_data


# ===================== 异步任务结果统一处理 =====================

def save_async_results(all_texts: list[str], all_json_data: list[dict[str, Any]], config: dict[str, Any], pdf_path: str, content_format: str, skip: list[str] | None = None) -> None:
    """异步任务结果统一处理：JSON保存 + raw保存 + 后处理"""
    model_key = config["model_key"]
    basename = os.path.splitext(pdf_path)[0]

    # --- 保存 JSON 结构化结果 ---
    json_out = f"{basename}_{model_key}.json"
    with open(json_out, "w", encoding="utf-8") as f:
        json.dump({
            "source": pdf_path,
            "model": model_key,
            "total_pages": len(all_texts),
            "pages": all_json_data
        }, f, ensure_ascii=False, indent=2)
    print(f"\n📋 JSON 结果已保存: {json_out}")

    # --- 保存原始结果（每页/结果用分隔线隔开） ---
    raw_out = f"{basename}_{model_key}_raw.txt"
    with open(raw_out, "w", encoding="utf-8") as f:
        for i, text in enumerate(all_texts):
            f.write(f"\n{'='*60}\n")
            if content_format in ("paddleocr_async", "pp-ocrv6"):
                f.write(f"第 {i+1} 条 (共 {len(all_texts)} 条)\n")
            else:
                f.write(f"结果 {i+1} (共 {len(all_texts)} 个)\n")
            f.write(f"{'='*60}\n\n")
            f.write(text)
            f.write("\n\n")
    print(f"\n📝 原始结果已保存: {raw_out}")

    # --- 后处理 ---
    print("\n🔧 后处理...")
    full_text = "\n\n".join(all_texts)
    full_text = postprocess.process(full_text, skip=skip)

    out = f"{basename}_{model_key}.txt"
    with open(out, "w", encoding="utf-8") as f:
        f.write(full_text)

    print(f"\n✅ 完成！总计 {len(full_text)} 字符 → {out}")
    if content_format in ("paddleocr_async", "pp-ocrv6"):
        print(f"   共处理 {len(all_texts)} 条结果")


# ===================== 子流程函数 =====================

import argparse


def build_parser() -> argparse.ArgumentParser:
    """构建标准命令行参数解析器"""
    parser = argparse.ArgumentParser(
        prog=version.NAME,
        description=version.version_banner(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
更多信息: {version.URL}
配置文件格式: models_config.toml (TOML)
外部配置热插拔: --config my_models.toml
        """.strip(),
    )
    parser.add_argument("pdf", nargs="?", default="document.pdf",
                        help="PDF 文件路径（默认: %(default)s）")
    parser.add_argument("-m", "--model", default=None,
                        help=f"模型名称（默认: {DEFAULT_MODEL}）")
    parser.add_argument("-s", "--skip", default=None,
                        help="跳过后处理模块，逗号分隔（如: dedup,fullwidth_punct）")
    parser.add_argument("-c", "--config", default=None,
                        help="外部 TOML 配置文件路径（热插拔新模型）")
    parser.add_argument("-v", "--version", action="store_true",
                        help="显示版本信息")
    parser.add_argument("-l", "--list-models", action="store_true",
                        help="列出所有可用模型并退出")
    parser.add_argument("--dpi", type=int, default=300,
                        help="PDF 渲染 DPI（默认: %(default)s）")
    parser.add_argument("--max-width", type=int, default=1600,
                        help="图片最大宽度（默认: %(default)s px）")
    return parser


def parse_skip_args(skip_str: str | None) -> list[str]:
    """解析 --skip 参数，返回要跳过的模块名列表"""
    if not skip_str:
        return []
    return [s.strip() for s in skip_str.split(",")]


def run_async_ocr(config: dict[str, Any], pdf_path: str) -> tuple[list[str], list[dict[str, Any]]]:
    """运行异步 OCR 任务，返回 (all_texts, all_json_data)"""
    content_format = config["content_format"]

    if content_format in ("paddleocr_async", "pp-ocrv6"):
        label = "PaddleOCR-VL-1.6" if content_format == "paddleocr_async" else "PP-OCRv6"
        print(f"🔧 {label} 异步任务模式")
        print("   直接上传PDF文件，无需预先转图片\n")
        return run_paddleocr_async(config, pdf_path)

    elif content_format == "mineru_async":
        print("🔧 MinerU Precision Extract API (v4)")
        print("   申请上传URL -> PUT上传 -> 轮询结果 -> 下载zip提取markdown\n")
        return mineru_ocr(config, pdf_path)

    else:
        raise ValueError(f"未知异步格式: {content_format}")


def run_llm_ocr(config: dict[str, Any], pdf_path: str, skip: list[str] | None = None) -> None:
    """运行 LLM OCR 模式：PDF转图片 -> 分批OCR -> 保存结果"""
    model_key = config["model_key"]
    batch_size = config.get("batch_size", 1)
    basename = os.path.splitext(pdf_path)[0]

    # 输入模式分流：原生支持 PDF 的模型直传每页 PDF，否则栅格化为图片
    input_mode = config.get("input_mode", "image")
    if input_mode == "pdf":
        print("📄 逐页直传原生 PDF（input_mode=pdf）...")
        all_blocks, total_pages = pdf_pages_to_pdf_b64(pdf_path)
    else:
        print("🔧 PDF 转图片（input_mode=image）...")
        all_blocks, total_pages = pdf_pages_to_b64(pdf_path)
    print(f"\n🚀 开始OCR（共{total_pages}页）...")

    # 分批运行OCR
    all_texts = []
    step = batch_size
    for start in range(0, total_pages, step):
        end = min(start + batch_size, total_pages)
        batch_images = all_blocks[start:end]
        batch_info = f"第{start+1}-{end}页 (共{total_pages}页)"
        print(f"\n📦 批次 {len(all_texts)+1}: {batch_info}")

        try:
            text = ocr_batch(config, batch_images, batch_info)
            all_texts.append(text)
        except Exception as e:
            print(f"❌ 批次 {len(all_texts)+1} 最终失败: {e}")
            all_texts.append(f"\n\n[第{start+1}-{end}页识别失败]\n\n")

    # 保存原始结果
    raw_out = f"{basename}_{model_key}_raw.txt"
    with open(raw_out, "w", encoding="utf-8") as f:
        for i, text in enumerate(all_texts):
            f.write(f"\n{'='*60}\n")
            f.write(f"批次 {i+1} (共 {len(all_texts)} 批)\n")
            f.write(f"{'='*60}\n\n")
            f.write(text)
            f.write("\n\n")
    print(f"\n📝 原始结果已保存: {raw_out}")

    # 后处理
    print("\n🔧 后处理...")
    full_text = "\n\n".join(all_texts)
    full_text = postprocess.process(full_text, skip=skip)

    out = f"{basename}_{model_key}.txt"
    with open(out, "w", encoding="utf-8") as f:
        f.write(full_text)

    print(f"\n✅ 完成！总计 {len(full_text)} 字符 → {out}")
    print(f"   共处理 {len(all_texts)} 个批次")


def main() -> None:
    """主入口：参数解析 -> 模型加载 -> 模式分发 -> 保存结果"""
    parser = build_parser()

    # 没有参数时显示 help
    if len(sys.argv) == 1:
        parser.print_help()
        return

    args = parser.parse_args()

    # --version
    if args.version:
        print(version.version_info())
        return

    # --list-models
    if args.list_models:
        print(f"可用模型（共 {len(CONFIGS)} 个）:\n")
        for key, cfg in CONFIGS.items():
            note = f" — {cfg.get('note', '')}" if cfg.get('note') else ""
            default = " ← 默认" if key == DEFAULT_MODEL else ""
            print(f"  {key:30s} {cfg['name']}{note}{default}")
        return

    print(f"\n🚀 {version.version_banner()}\n")

    pdf_path = args.pdf
    dpi = args.dpi
    max_width = args.max_width

    if not os.path.exists(pdf_path):
        print(f"❌ 找不到: {pdf_path}")
        sys.exit(1)

    # 加载外部配置（热插拔）
    if args.config:
        from models_config import load_configs
        load_configs(args.config)

    config = load_model_config(args.model)
    skip_args = parse_skip_args(args.skip)
    content_format = config.get("content_format", "openai")
    is_async = content_format in ("paddleocr_async", "pp-ocrv6", "mineru_async")

    # 打印概要信息
    print(f"📄 处理: {pdf_path}")
    print(f"🤖 模型: {config['name']} ({config['model_key']})")
    if args.config:
        print(f"📦 外部配置: {args.config}")
    if skip_args:
        print(f"⏭️  跳过处理模块: {', '.join(skip_args)}")
    if not is_async:
        batch_size = config.get("batch_size", 1)
        print(f"⚙️  每批{batch_size}页, DPI={dpi}")
    if "note" in config:
        print(f"📝 {config['note']}")
    print()

    # 模式分发
    if is_async:
        try:
            all_texts, all_json_data = run_async_ocr(config, pdf_path)
        except Exception as e:
            model_name = config["content_format"]
            print(f"❌ {model_name} 处理失败: {e}")
            sys.exit(1)
        save_async_results(all_texts, all_json_data, config, pdf_path, content_format, skip=skip_args)
    else:
        run_llm_ocr(config, pdf_path, skip=skip_args)


if __name__ == "__main__":
    main()
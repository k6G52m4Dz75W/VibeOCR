import requests
import base64
import sys
import os
import time
import json
import zipfile
import tempfile
from typing import Any

try:
    import fitz
    from PIL import Image
    from io import BytesIO
except ImportError:
    print("pip install pymupdf pillow")
    sys.exit(1)

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
    from openai import OpenAI
    OPENAI_AVAILABLE: bool = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    from models_config import CONFIGS, DEFAULT_MODEL
except ImportError:
    print("请将 models_config.py 放在同一目录下")
    sys.exit(1)

try:
    import config as config_module
except ImportError:
    config_module = None


def load_model_config(model_key: str | None = None) -> dict[str, Any]:
    """加载模型配置，支持从参数、环境变量或 config.py 读取"""
    if model_key is None:
        model_key = os.environ.get("OCR_MODEL", DEFAULT_MODEL)

    if model_key not in CONFIGS:
        print(f"❌ 未知模型配置: {model_key}")
        print(f"可用配置: {', '.join(CONFIGS.keys())}")
        sys.exit(1)

    config = CONFIGS[model_key].copy()

    api_key_env = config["api_key_env"]
    api_key = os.environ.get(api_key_env)

    if not api_key and config_module:
        api_key = getattr(config_module, api_key_env, None)

    if not api_key:
        print(f"⚠️  警告: API Key 未配置")
        print(f"   环境变量: export {api_key_env}=your_key")
        if config_module:
            print(f"   或修改 config.py 中的 {api_key_env}")
        sys.exit(1)

    config["api_key"] = api_key
    config["model_key"] = model_key

    return config


def build_payload(config: dict[str, Any], content: list[dict[str, Any]], batch_info: str) -> dict[str, Any]:
    """根据供应商格式构建请求体"""
    prompt = config.get("prompt", "请提取图片中的文本内容。")
    model_id = config["model_id"]
    template = config["payload_template"].copy()
    fmt = config["content_format"]

    if fmt == "anthropic":
        payload = {
            "model": model_id,
            "messages": [{"role": "user", "content": content}],
            **template
        }
    else:
        messages = [{"role": "user", "content": content}]
        payload = {
            "model": model_id,
            "messages": messages,
            **template
        }

    return payload


def build_headers(config: dict[str, Any]) -> dict[str, str]:
    """构建请求头"""
    headers = config["headers"].copy()
    headers["Authorization"] = f"Bearer {config['api_key']}"
    return headers


def pdf_pages_to_b64(pdf_path: str, dpi: int = 300, max_width: int = 1600) -> tuple[list[dict[str, Any]], int]:
    doc = fitz.open(pdf_path)
    total = len(doc)
    images = []

    for i in range(total):
        page = doc[i]
        pix = page.get_pixmap(matrix=fitz.Matrix(dpi/72, dpi/72))
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        if img.width > max_width:
            ratio = max_width / img.width
            new_height = int(img.height * ratio)
            img = img.resize((max_width, new_height), Image.LANCZOS)

        buf = BytesIO()
        img.save(buf, format="PNG", optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode()

        images.append({
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64," + b64}
        })
        size_kb = len(buf.getvalue()) / 1024
        print(f"  第{i+1}/{total}页已编码 ({int(size_kb)}KB)")

    doc.close()
    return images, total


def ocr_batch(config: dict[str, Any], images: list[dict[str, Any]], batch_info: str, max_retries: int = 3, retry_delay: int = 5) -> str:
    """发送一批图片OCR请求，支持失败重试，支持 stream 和非 stream 模式
    优先使用 openai 库（如果可用且配置了 base_url），否则使用 requests"""
    prompt = config.get("prompt", "请提取图片中的文本内容。")
    content = [{"type": "text", "text": prompt + "\n\n【当前批次: " + batch_info + "】"}]
    content.extend(images)

    total_size = sum(len(img["image_url"]["url"]) for img in images)
    print(f"  总base64大小: {int(total_size/1024)}KB")

    payload = build_payload(config, content, batch_info)
    use_stream = payload.get("stream", False)

    # 判断是否可以使用 openai 库（需要 base_url 支持 OpenAI 兼容格式）
    api_url = config["api_url"]
    base_url = api_url.replace('/chat/completions', '')
    can_use_openai = OPENAI_AVAILABLE and config.get("content_format") == "openai"

    last_error = None
    for attempt in range(1, max_retries + 1):
        if can_use_openai:
            print(f"  发送请求 [openai库] (尝试 {attempt}/{max_retries}, stream={use_stream})...", end=" ")
        else:
            print(f"  发送请求 [requests] (尝试 {attempt}/{max_retries}, stream={use_stream})...", end=" ")
        try:
            if can_use_openai:
                # 使用 openai 库（更稳定，兼容性好）
                client = OpenAI(
                    api_key=config["api_key"],
                    base_url=base_url
                )

                # 构建消息（图片和文本顺序：图片在前，文本在后，与隔壁AI一致）
                message_content = []
                for img in images:
                    message_content.append(img)
                message_content.append({"type": "text", "text": prompt + "\n\n【当前批次: " + batch_info + "】"})

                response = client.chat.completions.create(
                    model=config["model_id"],
                    messages=[{"role": "user", "content": message_content}],
                    stream=use_stream,
                    max_tokens=payload.get("max_tokens", 4096),
                    temperature=payload.get("temperature", 0.2),
                    top_p=payload.get("top_p", 1.0)
                )

                if use_stream:
                    text = ""
                    for chunk in response:
                        if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                            text += chunk.choices[0].delta.content
                    print(f"✅ {len(text)}字符 (openai流式)")
                else:
                    text = response.choices[0].message.content
                    print(f"✅ {len(text)}字符 (openai非流式)")
            else:
                # 使用 requests 手动发送（原有逻辑）
                headers = build_headers(config)
                timeout = config["timeout"]
                resp = requests.post(api_url, headers=headers, json=payload, timeout=timeout, stream=use_stream)
                resp.raise_for_status()

                if use_stream:
                    text = ""
                    for line in resp.iter_lines():
                        if line:
                            line_str = line.decode('utf-8')
                            if line_str.startswith('data: '):
                                data_str = line_str[6:]
                                if data_str == '[DONE]':
                                    break
                                try:
                                    chunk = json.loads(data_str)
                                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                                    if delta.get("content"):
                                        text += delta["content"]
                                except json.JSONDecodeError:
                                    continue
                    print(f"✅ {len(text)}字符 (requests流式)")
                else:
                    data = resp.json()
                    fmt = config["content_format"]
                    if fmt == "anthropic":
                        text = data["content"][0]["text"]
                    else:
                        text = data["choices"][0]["message"]["content"]
                    print(f"✅ {len(text)}字符 (requests非流式)")

            return text
        except Exception as e:
            last_error = e
            print(f"❌ 失败: {e}")
            if attempt < max_retries:
                print(f"  ⏳ {retry_delay}秒后重试...")
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                print(f"  💥 已达到最大重试次数，放弃")

    raise last_error


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
    - PP-OCRv6: result.ocrResults[].text + .ocrImage
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
            ocr_results = result.get("ocrResults", [])
            for res in ocr_results:
                text = res.get("text", "")
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
    if config["content_format"] == "paddleocr_v6":
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
            {"name": file_name}
        ],
        "model_version": template.get("model_version", "vlm"),
        "is_ocr": template.get("is_ocr", True),
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
            if content_format in ("paddleocr_async", "paddleocr_v6"):
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
    if content_format in ("paddleocr_async", "paddleocr_v6"):
        print(f"   共处理 {len(all_texts)} 条结果")


# ===================== 子流程函数 =====================

def parse_model_key() -> str | None:
    """从命令行参数解析 --model，返回 model_key"""
    for i, arg in enumerate(sys.argv):
        if arg == "--model" and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


def parse_config_path() -> str | None:
    """从命令行参数解析 --config，返回外部 TOML 配置文件路径"""
    for i, arg in enumerate(sys.argv):
        if arg == "--config" and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


def parse_skip_args() -> list[str]:
    """从命令行参数解析 --skip，返回要跳过的模块名列表"""
    for i, arg in enumerate(sys.argv):
        if arg == "--skip" and i + 1 < len(sys.argv):
            return [s.strip() for s in sys.argv[i + 1].split(",")]
    return []


def run_async_ocr(config: dict[str, Any], pdf_path: str) -> tuple[list[str], list[dict[str, Any]]]:
    """运行异步 OCR 任务，返回 (all_texts, all_json_data)"""
    content_format = config["content_format"]

    if content_format in ("paddleocr_async", "paddleocr_v6"):
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

    # PDF转图片
    print("🔧 PDF转图片...")
    all_images, total_pages = pdf_pages_to_b64(pdf_path)
    print(f"\n🚀 开始OCR（共{total_pages}页）...")

    # 分批运行OCR
    all_texts = []
    step = batch_size
    for start in range(0, total_pages, step):
        end = min(start + batch_size, total_pages)
        batch_images = all_images[start:end]
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
    # 处理 --version
    if "--version" in sys.argv:
        print(version.version_info())
        return

    print(f"\n🚀 {version.version_banner()}\n")

    pdf_path = sys.argv[1] if len(sys.argv) > 1 else "document.pdf"
    dpi = 300
    max_width = 1600

    if not os.path.exists(pdf_path):
        print(f"❌ 找不到: {pdf_path}")
        sys.exit(1)

    # 加载外部配置（热插拔）
    config_path = parse_config_path()
    if config_path:
        from models_config import load_configs
        load_configs(config_path)

    config = load_model_config(parse_model_key())
    skip_args = parse_skip_args()
    content_format = config.get("content_format", "openai")
    is_async = content_format in ("paddleocr_async", "paddleocr_v6", "mineru_async")

    # 打印概要信息
    print(f"📄 处理: {pdf_path}")
    print(f"🤖 模型: {config['name']} ({config['model_key']})")
    if config_path:
        print(f"📦 外部配置: {config_path}")
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
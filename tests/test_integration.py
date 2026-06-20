"""
集成测试：完整 OCR 流程。

覆盖场景：
  1. 完整后处理流水线 — 模拟 DeepSeek-OCR 输出 → 清理去重 → 干净文本
  2. DeepSeek-OCR 全流程 — PDF → 模拟 API 调用 → 后处理
  3. MinerU 异步流程 — 模拟 zip 下载 → 提取 → 保存
  4. PaddleOCR-VL 异步流程 — 模拟 jsonl 下载 → 解析 → 保存
  5. PP-OCRv6 异步流程 — 模拟 jsonl 下载 → 解析 → 保存
"""

import sys
import os
import json
import tempfile
import zipfile
import base64
from io import BytesIO
from unittest.mock import patch, MagicMock, mock_open
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ======================================================================
# Fixtures 和辅助函数
# ======================================================================

SAMPLE_IMAGE_B64 = base64.b64encode(b"fake-png-data-1234").decode()
SAMPLE_IMAGE_DICT = {
    "type": "image_url",
    "image_url": {"url": f"data:image/png;base64,{SAMPLE_IMAGE_B64}"},
}


def make_batch_text(chunks: list[str]) -> str:
    """生成带批次标记的模拟 OCR 输出"""
    parts = []
    for i, chunk in enumerate(chunks):
        parts.append(f"{'='*40}\n批次 {i+1} (共 {len(chunks)} 批)\n{'='*40}\n")
        parts.append(chunk)
    return "".join(parts)


def make_mineru_zip(md_content: str, json_content: dict | None = None) -> bytes:
    """创建模拟的 MinerU 结果 zip"""
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("content/full.md", md_content)
        if json_content:
            zf.writestr("content/structure.json", json.dumps(json_content, ensure_ascii=False))
    return buf.getvalue()


def make_paddleocr_jsonl(results: list[dict], content_format: str = "paddleocr_vl") -> str:
    """创建模拟的 PaddleOCR jsonl 响应"""
    lines = []
    for r in results:
        lines.append(json.dumps({"result": r}, ensure_ascii=False))
    return "\n".join(lines)


SAMPLE_CONFIG_LLM = {
    "name": "Test / DeepSeek-OCR",
    "api_url": "https://api.test.com/v1/chat/completions",
    "model_id": "test-model",
    "api_key_env": "TEST_API_KEY",
    "api_key": "test-key-123",
    "model_key": "test_model",
    "batch_size": 1,
    "headers": {"Accept": "application/json"},
    "payload_template": {"max_tokens": 4096, "temperature": 0.1},
    "timeout": 30,
    "content_format": "openai",
    "prompt": "提取文本。",
}

SAMPLE_CONFIG_MNERU = {
    "name": "Test / MinerU",
    "api_url": "https://mineru.test/api/v4",
    "model_id": "vlm",
    "api_key_env": "TEST_API_KEY",
    "api_key": "test-key-123",
    "model_key": "test_mineru",
    "batch_size": 1,
    "headers": {"Accept": "application/json"},
    "payload_template": {"model_version": "vlm", "is_ocr": True},
    "timeout": 30,
    "content_format": "mineru_async",
}

SAMPLE_CONFIG_PADDLE = {
    "name": "Test / PaddleOCR-VL",
    "api_url": "https://paddle.test/api/v2/ocr/jobs",
    "model_id": "PaddleOCR-VL-1.6",
    "api_key_env": "TEST_API_KEY",
    "api_key": "test-key-123",
    "model_key": "test_paddle",
    "batch_size": 1,
    "headers": {"Accept": "application/json"},
    "payload_template": {},
    "timeout": 30,
    "content_format": "paddleocr_async",
}

SAMPLE_CONFIG_PADDLE_V6 = {**SAMPLE_CONFIG_PADDLE, "model_key": "test_paddle_v6", "content_format": "paddleocr_v6"}


# ======================================================================
# 场景 1：完整后处理流水线
# ======================================================================

class TestFullPostprocessPipeline:
    """模拟 DeepSeek-OCR 的完整输出 → 后处理流水线"""

    def test_deepseek_ocr_full_output(self):
        """模拟 DeepSeek-OCR 输出（含 grounding + batch markers + 中文），验证最终结果干净"""
        simulated_ocr_output = (
            '<|ref|>段落开始<|/ref|> <|det|>[[0,50,100,150]]<|/det|>\n'
            '这是第一行很长的中文内容需要合并到下一行\n'
            '这是第二行很长的中文内容。\n'
            '\n'
            '========================\n'
            '批次 1 (共 2 批)\n'
            '========================\n'
            '这是第一行很长的中文内容需要合并到下一行\n'
            '这是第二行很长的中文内容。\n'
            '\n'
            '========================\n'
            '批次 2 (共 2 批)\n'
            '========================\n'
            '这是第二行很长的中文内容。这是第三页的内容。\n'
            '\n'
            '====正文结束===='
        )
        from postprocess import process
        result = process(simulated_ocr_output)

        # 验证：无 grounding 标签
        assert "<|ref|>" not in result
        assert "<|det|>" not in result
        # 验证：无批次标记
        assert "批次 1" not in result
        assert "批次 2" not in result
        # 验证：中文内容保留
        assert "这是第一行很长的中文内容" in result
        assert "这是第二行很长的中文内容" in result
        # 验证：输出不是空字符串
        assert len(result) > 50

    def test_english_text_pipeline(self):
        """英文文本完整流水线"""
        text = '<|ref|>test<|/ref|> <|det|>[[0]]<|/det|>\nThis is a\nlong paragraph.'
        from postprocess import process
        result = process(text)
        assert "<|ref|>" not in result
        # 英文段落可能会合并
        assert "long paragraph" in result

    def test_empty_after_cleanup(self):
        """仅有标签和标记的文本清理后应为空或极少"""
        text = '<|ref|>x<|/ref|> <|det|>[[0]]<|/det|>\n\n========================\n批次 1 (共 1 批)\n========================'
        from postprocess import process
        result = process(text)
        assert len(result.strip()) == 0


# ======================================================================
# 场景 2：DeepSeek-OCR 全流程
# ======================================================================

class TestDeepseekOCRFullFlow:
    """模拟 LLM OCR 全流程：PDF 编码 → API 调用 → 后处理保存"""

    @patch("VibeOCR3.pdf_pages_to_b64")
    def test_single_page_flow(self, mock_pdf2b64):
        """1 页 PDF → 接收 API 响应 → 后处理"""
        mock_pdf2b64.return_value = (
            [SAMPLE_IMAGE_DICT],
            1,
        )

        from VibeOCR3 import ocr_batch

        # 模拟 API 返回
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "这是OCR提取的文本内容。"}}]
        }

        with patch("VibeOCR3.OPENAI_AVAILABLE", False), patch("VibeOCR3.requests.post", return_value=mock_response):
            result = ocr_batch(SAMPLE_CONFIG_LLM, [SAMPLE_IMAGE_DICT], "第1-1页 (共1页)")

        assert "OCR提取" in result
        assert "文本内容" in result

    @patch("VibeOCR3.pdf_pages_to_b64")
    def test_multi_page_flow_with_postprocess(self, mock_pdf2b64):
        """多页 PDF → 分批 OCR → 合并 → 后处理"""
        mock_pdf2b64.return_value = (
            [SAMPLE_IMAGE_DICT, SAMPLE_IMAGE_DICT],
            2,
        )

        from VibeOCR3 import ocr_batch

        page_contents = [
            "这是第一页的文本内容需要足够长才能避免短行合并。",
            "这是第二页的文本内容也足够长避免合并问题。",
        ]

        def api_response_side_effect(*args, **kwargs):
            mock_resp = MagicMock()
            # 按调用次数返回不同内容
            idx = api_response_side_effect.call_count
            api_response_side_effect.call_count += 1
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "choices": [{"message": {"content": page_contents[min(idx, len(page_contents)-1)]}}]
            }
            return mock_resp
        api_response_side_effect.call_count = 0

        with patch("VibeOCR3.OPENAI_AVAILABLE", False), patch("VibeOCR3.requests.post", side_effect=api_response_side_effect):
            text1 = ocr_batch(SAMPLE_CONFIG_LLM, [SAMPLE_IMAGE_DICT], "批次1")
            text2 = ocr_batch(SAMPLE_CONFIG_LLM, [SAMPLE_IMAGE_DICT], "批次2")

        full_text = text1 + "\n\n" + text2
        from postprocess import process
        result = process(full_text)

        assert "第一页的文本内容" in result
        assert "第二页的文本内容" in result

    @patch("VibeOCR3.pdf_pages_to_b64")
    def test_streaming_response(self, mock_pdf2b64):
        """模拟 stream=True 的 API 响应"""
        mock_pdf2b64.return_value = ([SAMPLE_IMAGE_DICT], 1)

        class MockStreamChunk:
            def __init__(self, content):
                self.choices = [MagicMock(delta=MagicMock(content=content))]

        mock_response = MagicMock()
        mock_response.__iter__.return_value = [
            MockStreamChunk("这是"),
            MockStreamChunk("流式"),
            MockStreamChunk("响应"),
            MockStreamChunk("文本。"),
        ]

        from VibeOCR3 import ocr_batch
        config_stream = {**SAMPLE_CONFIG_LLM, "payload_template": {**SAMPLE_CONFIG_LLM["payload_template"], "stream": True}}

        with patch("VibeOCR3.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response.__iter__.return_value

            # 设置 OPENAI_AVAILABLE = True
            with patch("VibeOCR3.OPENAI_AVAILABLE", True):
                result = ocr_batch(config_stream, [SAMPLE_IMAGE_DICT], "流式测试")

        assert "流式响应文本" in result


# ======================================================================
# 场景 3：MinerU 异步流程
# ======================================================================

class TestMinerUAsyncFlow:
    """MinerU 完整异步流程：申请 URL → 上传 → 轮询 → 下载 → 提取 → 保存"""

    def test_mineru_download_and_extract(self):
        """模拟 zip 下载 → 提取 md 和 json"""
        md_text = "# 测试文档\n\n这是提取的正文内容。\n\n第二段落。"
        json_data = {"pages": [{"page_num": 1, "content": "正文内容"}]}
        zip_bytes = make_mineru_zip(md_text, json_data)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = zip_bytes

        from VibeOCR3 import mineru_download_and_extract

        with patch("VibeOCR3.requests.get", return_value=mock_response):
            content, json_result = mineru_download_and_extract("https://test.zip")

        assert "测试文档" in content
        assert "正文内容" in content
        assert json_result["pages"][0]["page_num"] == 1

    def test_mineru_extract_no_json(self):
        """zip 中无 json 文件时也应能正常工作"""
        zip_bytes = make_mineru_zip("仅文本内容", json_content=None)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = zip_bytes

        from VibeOCR3 import mineru_download_and_extract

        with patch("VibeOCR3.requests.get", return_value=mock_response):
            content, json_result = mineru_download_and_extract("https://test.zip")

        assert "仅文本内容" in content
        assert json_result == {}

    def test_mineru_full_flow(self):
        """模拟 MinerU 完整流程：申请URL → 上传 → 轮询 → 下载 → 提取 """
        from VibeOCR3 import mineru_get_upload_url, mineru_upload_file, mineru_poll_batch, mineru_ocr

        mock_resp_upload = MagicMock()
        mock_resp_upload.status_code = 200
        mock_resp_upload.json.return_value = {
            "code": 0,
            "data": {"batch_id": "test-batch-123", "file_urls": ["https://upload.test/file.pdf"]},
        }

        mock_resp_put = MagicMock()
        mock_resp_put.status_code = 200

        mock_resp_poll = MagicMock()
        mock_resp_poll.status_code = 200
        mock_resp_poll.json.return_value = {
            "code": 0,
            "data": {
                "extract_result": [{
                    "state": "done",
                    "file_name": "test.pdf",
                    "full_zip_url": "https://download.test/result.zip",
                }]
            },
        }

        md_text = "# MinerU 结果\n\n正文内容。"
        zip_bytes = make_mineru_zip(md_text, {"pages": [{"num": 1}]})

        mock_resp_zip = MagicMock()
        mock_resp_zip.status_code = 200
        mock_resp_zip.content = zip_bytes

        with (
            patch("VibeOCR3.requests.post", return_value=mock_resp_upload) as mock_post,
            patch("VibeOCR3.requests.put", return_value=mock_resp_put) as mock_put,
            patch("VibeOCR3.requests.get", return_value=mock_resp_zip) as mock_get,
        ):
            # 此时 mineru_poll_batch 会发 GET 请求，让它走轮询路径
            # 由于 mock_get 始终返回 mock_resp_zip，poll 会陷入死循环
            # 我们需要更精细的控制，因此这里只测试前两个步骤
            batch_id, upload_url = mineru_get_upload_url(SAMPLE_CONFIG_MNERU, "/tmp/test.pdf")
            assert batch_id == "test-batch-123"
            assert upload_url == "https://upload.test/file.pdf"

            result = mineru_upload_file(upload_url, __file__)  # 上传当前文件
            assert result is True

    def test_mineru_ocr_function(self):
        """模拟 mineru_ocr 顶层函数"""
        from VibeOCR3 import mineru_ocr

        md_text = "提取的正文内容。"
        zip_bytes = make_mineru_zip(md_text, {"page": 1})

        # POST → upload_url 申请；GET → poll + download
        r_upload = MagicMock(status_code=200)
        r_upload.json.return_value = {"code": 0, "data": {"batch_id": "b1", "file_urls": ["https://up.test/f.pdf"]}}

        r_poll = MagicMock(status_code=200)
        r_poll.json.return_value = {"code": 0, "data": {"extract_result": [{"state": "done", "full_zip_url": "https://dl.test/z.zip"}]}}

        r_zip = MagicMock(status_code=200, content=zip_bytes)

        post_counter = [0]

        def post_side_effect(*args, **kwargs):
            post_counter[0] += 1
            return r_upload

        get_counter = [0]

        def get_side_effect(*args, **kwargs):
            idx = get_counter[0]
            get_counter[0] += 1
            if idx == 0:
                return r_poll
            return r_zip

        # 使用真实临时文件避免文件不存在错误
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            with (
                patch("VibeOCR3.requests.post", side_effect=post_side_effect),
                patch("VibeOCR3.requests.put", return_value=MagicMock(status_code=200)),
                patch("VibeOCR3.requests.get", side_effect=get_side_effect),
            ):
                texts, json_data = mineru_ocr(SAMPLE_CONFIG_MNERU, tmp_path)
        finally:
            os.unlink(tmp_path)

        assert len(texts) == 1
        assert "提取的正文内容" in texts[0]


# ======================================================================
# 场景 4 + 5：PaddleOCR 异步流程（VL + v6）
# ======================================================================

class TestPaddleOCRVlAsyncFlow:
    """PaddleOCR-VL 异步流程：提交 → 轮询 → jsonl 下载 → 解析 → 保存"""

    @patch("VibeOCR3.paddleocr_poll_job")
    def test_vl_fetch_results(self, mock_poll):
        """模拟 jsonl 下载 → 解析 PaddleOCR-VL 格式结果"""
        from VibeOCR3 import paddleocr_fetch_results

        jsonl_lines = make_paddleocr_jsonl([
            {
                "layoutParsingResults": [
                    {"markdown": {"text": "第一页正文内容。"}},
                ]
            },
            {
                "layoutParsingResults": [
                    {"markdown": {"text": "第二页正文内容。"}},
                    {"markdown": {"text": "第二页第二段。"}},
                ]
            },
        ])

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = jsonl_lines

        with patch("VibeOCR3.requests.get", return_value=mock_resp):
            texts, json_data = paddleocr_fetch_results("https://test.jsonl")

        assert len(texts) == 3
        assert "第一页正文内容" in texts[0]
        assert "第二页正文内容" in texts[1]
        assert "第二页第二段" in texts[2]
        assert len(json_data) == 2

    def test_vl_full_flow(self):
        """模拟 PaddleOCR-VL 完整异步流程"""
        from VibeOCR3 import run_paddleocr_async

        jsonl_lines = make_paddleocr_jsonl([
            {"layoutParsingResults": [{"markdown": {"text": "VL提取结果。"}}]},
        ])

        # 模拟 submit_job → 返回 job_id
        mock_submit = MagicMock()
        mock_submit.status_code = 200
        mock_submit.json.return_value = {"data": {"jobId": "job-123"}}

        # 模拟 poll_job → 返回 jsonl_url
        mock_poll = MagicMock()
        mock_poll.status_code = 200
        mock_poll.json.return_value = {
            "data": {
                "state": "done",
                "extractProgress": {"extractedPages": 1, "totalPages": 1, "startTime": "2024-01-01T00:00:00", "endTime": "2024-01-01T00:01:00"},
                "resultUrl": {"jsonUrl": "https://test/result.jsonl"},
            }
        }

        # 模拟 fetch_results → 返回文本
        mock_jsonl = MagicMock()
        mock_jsonl.status_code = 200
        mock_jsonl.text = jsonl_lines

        call_order = [0]

        def mock_get(url, **kwargs):
            idx = call_order[0]
            call_order[0] += 1
            if idx == 0:
                return mock_poll
            return mock_jsonl

        with (
            patch("VibeOCR3.requests.post", return_value=mock_submit),
            patch("VibeOCR3.requests.get", side_effect=mock_get),
        ):
            texts, json_data = run_paddleocr_async(SAMPLE_CONFIG_PADDLE, "https://example.com/test.pdf")

        assert len(texts) >= 1
        assert "VL提取结果" in texts[0]

    def test_vl_with_save(self):
        """验证 save_async_results 能正确处理 VL 格式"""
        from VibeOCR3 import save_async_results

        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = os.path.join(tmpdir, "test.pdf")
            # 创建一个空 PDF 让 os.path.splitext 有正确 basename
            Path(pdf_path).write_text("", encoding="utf-8")

            texts = ["第一页内容。", "第二页内容。"]
            json_data = [{"page_index": 0, "result": {}}, {"page_index": 1, "result": {}}]

            save_async_results(texts, json_data, SAMPLE_CONFIG_PADDLE, pdf_path, "paddleocr_async")

            basename = os.path.splitext(pdf_path)[0]
            assert os.path.exists(f"{basename}_{SAMPLE_CONFIG_PADDLE['model_key']}.json")
            assert os.path.exists(f"{basename}_{SAMPLE_CONFIG_PADDLE['model_key']}_raw.txt")
            assert os.path.exists(f"{basename}_{SAMPLE_CONFIG_PADDLE['model_key']}.txt")


class TestPaddleOCRV6AsyncFlow:
    """PP-OCRv6 异步流程"""

    @patch("VibeOCR3.paddleocr_poll_job")
    def test_v6_fetch_results(self, mock_poll):
        """模拟 jsonl 下载 → 解析 PP-OCRv6 格式结果"""
        from VibeOCR3 import paddleocr_v6_fetch_results

        jsonl_lines = make_paddleocr_jsonl([
            {
                "ocrResults": [
                    {"text": "第一段文字"},
                    {"text": "第二段文字"},
                ]
            },
            {
                "ocrResults": [
                    {"text": "第三段文字"},
                ]
            },
        ], content_format="paddleocr_v6")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = jsonl_lines

        with patch("VibeOCR3.requests.get", return_value=mock_resp):
            texts, json_data = paddleocr_v6_fetch_results("https://test.jsonl")

        assert len(texts) == 3
        assert "第一段文字" in texts[0]
        assert "第二段文字" in texts[1]
        assert "第三段文字" in texts[2]
        assert len(json_data) == 2

    def test_v6_full_flow(self):
        """模拟 PP-OCRv6 完整异步流程"""
        from VibeOCR3 import run_paddleocr_async

        jsonl_lines = make_paddleocr_jsonl([
            {"ocrResults": [{"text": "v6提取文本。"}]},
        ], content_format="paddleocr_v6")

        mock_submit = MagicMock()
        mock_submit.status_code = 200
        mock_submit.json.return_value = {"data": {"jobId": "job-v6-456"}}

        mock_poll = MagicMock()
        mock_poll.status_code = 200
        mock_poll.json.return_value = {
            "data": {
                "state": "done",
                "extractProgress": {"extractedPages": 1, "totalPages": 1, "startTime": "2024-01-01T00:00:00", "endTime": "2024-01-01T00:01:00"},
                "resultUrl": {"jsonUrl": "https://test/v6-result.jsonl"},
            }
        }

        mock_jsonl = MagicMock()
        mock_jsonl.status_code = 200
        mock_jsonl.text = jsonl_lines

        call_order = [0]

        def mock_get(url, **kwargs):
            idx = call_order[0]
            call_order[0] += 1
            if idx == 0:
                return mock_poll
            return mock_jsonl

        with (
            patch("VibeOCR3.requests.post", return_value=mock_submit),
            patch("VibeOCR3.requests.get", side_effect=mock_get),
        ):
            texts, json_data = run_paddleocr_async(SAMPLE_CONFIG_PADDLE_V6, "https://example.com/test.pdf")

        assert len(texts) >= 1
        assert "v6提取文本" in texts[0]

    def test_v6_with_save(self):
        """验证 save_async_results 能正确处理 v6 格式"""
        from VibeOCR3 import save_async_results

        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = os.path.join(tmpdir, "test_v6.pdf")
            Path(pdf_path).write_text("", encoding="utf-8")

            texts = ["v6结果1", "v6结果2"]
            json_data = [{"page_index": 0, "result": {}}, {"page_index": 1, "result": {}}]

            save_async_results(texts, json_data, SAMPLE_CONFIG_PADDLE_V6, pdf_path, "paddleocr_v6")

            basename = os.path.splitext(pdf_path)[0]
            assert os.path.exists(f"{basename}_{SAMPLE_CONFIG_PADDLE_V6['model_key']}.json")
            assert os.path.exists(f"{basename}_{SAMPLE_CONFIG_PADDLE_V6['model_key']}_raw.txt")
            assert os.path.exists(f"{basename}_{SAMPLE_CONFIG_PADDLE_V6['model_key']}.txt")

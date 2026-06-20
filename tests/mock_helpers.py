"""
Mock 测试工具：为 VibeOCR 集成测试提供可复用的模拟对象。

三大能力：
  1. Mock API 请求 — 快速构造带 json/content/text 的模拟 HTTP 响应
  2. Mock 轮询逻辑 — 状态机模拟 pending → running → done/failed 的完整生命周期
  3. Mock 文件下载 — 预定义的 zip / jsonl 构建工具
"""

import json
import zipfile
import base64
import time
from io import BytesIO
from unittest.mock import MagicMock
from typing import Any, Callable


# ======================================================================
# 1. Mock API 请求
# ======================================================================

def mock_response(
    status_code: int = 200,
    json_data: dict | None = None,
    text: str | None = None,
    content: bytes | None = None,
) -> MagicMock:
    """
    创建模拟的 HTTP 响应对象。

    用法:
        resp = mock_response(200, {"choices": [...]})
        resp.json()        → {"choices": [...]}
        resp.status_code   → 200
        resp.text          → ""  (默认空)
        resp.content       → b"" (默认空)
    """
    resp = MagicMock()
    resp.status_code = status_code
    resp.ok = 200 <= status_code < 300

    if json_data is not None:
        resp.json.return_value = json_data
    else:
        resp.json.return_value = {}

    resp.text = text or ""
    resp.content = content or b""

    return resp


def mock_openai_chunk(content: str, finish_reason: str | None = None) -> MagicMock:
    """创建模拟的 OpenAI 流式响应块"""
    chunk = MagicMock()
    choice = MagicMock()
    choice.delta.content = content
    choice.finish_reason = finish_reason
    chunk.choices = [choice]
    return chunk


def mock_openai_stream(chunks: list[str]) -> list[MagicMock]:
    """创建模拟的 OpenAI 流式响应迭代器"""
    return [mock_openai_chunk(c) for c in chunks]


# ======================================================================
# 2. Mock 轮询逻辑
# ======================================================================

class MockPoller:
    """
    状态机模拟器：模拟异步任务从 pending → running → done/failed 的完整生命周期。

    用法:
        poller = MockPoller(total_pages=3)
        resp = poller.poll()  # → {"state": "pending", ...}
        resp = poller.poll()  # → {"state": "running", ...}
        resp = poller.poll()  # → {"state": "done", "resultUrl": {...}}

    自定义状态序列:
        poller = MockPoller(sequence=["pending", "running", "running", "done"])
    """

    def __init__(
        self,
        total_pages: int = 1,
        extracted_pages: int | None = None,
        sequence: list[str] | None = None,
        result_url: str = "https://mock.test/result.jsonl",
        zip_url: str = "https://mock.test/result.zip",
        start_time: str = "2024-01-01T00:00:00",
        end_time: str = "2024-01-01T00:01:00",
    ):
        self.total_pages = total_pages
        self.extracted_pages = extracted_pages
        self.result_url = result_url
        self.zip_url = zip_url
        self.start_time = start_time
        self.end_time = end_time

        if sequence:
            self._sequence = list(sequence)
        else:
            # 默认：pending → running → done
            self._sequence = ["pending", "running", "done"]

        self._call_count = 0

    def _current_state(self) -> str:
        """返回当前状态，超出序列末尾则返回序列最后一个状态"""
        idx = min(self._call_count, len(self._sequence) - 1)
        return self._sequence[idx]

    def poll(self, *args, **kwargs) -> MagicMock:
        """
        生成一次轮询的模拟响应。
        每次调用推进一个状态。
        """
        state = self._current_state()
        self._call_count += 1
        return self._build_response(state)

    def _build_response(self, state: str) -> MagicMock:
        raise NotImplementedError("子类需实现 _build_response")


class MockPaddlePoller(MockPoller):
    """
    模拟 PaddleOCR 轮询响应。

    生成符合 paddleocr_poll_job 预期的 JSON 结构：
      {"data": {"state": "...", "extractProgress": {...}, "resultUrl": {...}}}
    """

    def _build_response(self, state: str) -> MagicMock:
        extract_progress = {
            "totalPages": self.total_pages,
            "extractedPages": self.extracted_pages or (
                0 if state == "pending" else
                self.total_pages if state == "done" else
                self.total_pages // 2
            ),
        }

        # done 状态必须包含 startTime/endTime/resultUrl
        data = {"state": state, "extractProgress": extract_progress}
        if state == "done":
            extract_progress["startTime"] = self.start_time
            extract_progress["endTime"] = self.end_time
            data["resultUrl"] = {"jsonUrl": self.result_url}

        return mock_response(200, {"data": data})


class MockMinerUPoller(MockPoller):
    """
    模拟 MinerU 轮询响应。

    生成符合 mineru_poll_batch 预期的 JSON 结构：
      {"code": 0, "data": {"extract_result": [{"state": "...", ...}]}}
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # MinerU 用 batch_id 查询，无默认 sequence
        if not hasattr(self, "_MockPoller__sequence"):
            self._sequence = ["pending", "running", "done"]

    def _build_response(self, state: str) -> MagicMock:
        item = {"state": state}

        if state == "done":
            item["full_zip_url"] = self.zip_url

        return mock_response(200, {
            "code": 0,
            "data": {"extract_result": [item]},
        })


def mock_failed_poll(error_msg: str = "任务处理失败") -> MagicMock:
    """创建模拟的失败轮询响应"""
    return mock_response(200, {
        "data": {"state": "failed", "message": error_msg},
    })


def mock_timeout_poll(timeout_after: float = 0.01) -> Callable:
    """
    模拟轮询超时：在连续返回 pending 一定次数后抛 TimeoutError。

    返回可传递给 patch 的 side_effect。
    实际场景应让轮询进入 sleep → wake 循环，最终因 timeout 参数触发。
    此 helper 通过快速抛出异常来模拟。
    """
    call_count = [0]

    def _poll(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] > 3:
            raise TimeoutError("轮询超时")
        return mock_response(200, {"data": {"state": "pending"}})

    return _poll


# ======================================================================
# 3. Mock 文件下载
# ======================================================================

def make_mineru_zip(md_content: str, json_content: dict | None = None) -> bytes:
    """创建模拟的 MinerU 结果 zip（含 content/full.md + 可选 content/structure.json）"""
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("content/full.md", md_content)
        if json_content:
            zf.writestr("content/structure.json", json.dumps(json_content, ensure_ascii=False))
    return buf.getvalue()


def make_paddleocr_jsonl(
    results: list[dict],
    content_format: str = "paddleocr_vl",
) -> str:
    """
    创建模拟的 PaddleOCR jsonl 响应。

    每条 JSONL 行结构: {"result": <条目>}
    """
    lines = []
    for r in results:
        lines.append(json.dumps({"result": r}, ensure_ascii=False))
    return "\n".join(lines)


def make_batch_text(chunks: list[str]) -> str:
    """生成带批次标记的模拟 OCR 输出"""
    parts = []
    for i, chunk in enumerate(chunks):
        parts.append(f"{'='*40}\n批次 {i+1} (共 {len(chunks)} 批)\n{'='*40}\n")
        parts.append(chunk)
    return "".join(parts)


# ======================================================================
# 4. 预定义样本数据
# ======================================================================

SAMPLE_IMAGE_B64 = base64.b64encode(b"fake-png-data-1234").decode()
SAMPLE_IMAGE_DICT = {
    "type": "image_url",
    "image_url": {"url": f"data:image/png;base64,{SAMPLE_IMAGE_B64}"},
}

SAMPLE_CONFIG_LLM = {
    "name": "Test / LLM Model",
    "api_url": "https://api.test.com/v1/chat/completions",
    "model_id": "test-model",
    "api_key_env": "TEST_API_KEY",
    "api_key": "test-key-123",
    "model_key": "test_llm",
    "batch_size": 1,
    "headers": {"Accept": "application/json"},
    "payload_template": {"max_tokens": 4096, "temperature": 0.1},
    "timeout": 30,
    "content_format": "openai",
    "prompt": "提取文本。",
}

SAMPLE_CONFIG_MINERU = {
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

SAMPLE_CONFIG_PADDLE_V6 = {
    **SAMPLE_CONFIG_PADDLE,
    "model_key": "test_paddle_v6",
    "content_format": "paddleocr_v6",
}


# ======================================================================
# 5. 便捷函数：完整流程模拟
# ======================================================================

def mock_paddle_submit_response(job_id: str = "mock-job-001") -> MagicMock:
    """模拟 PaddleOCR submit_job 的成功响应"""
    return mock_response(200, {"data": {"jobId": job_id}})


def mock_mineru_upload_response(batch_id: str = "mock-batch-001", upload_url: str = "https://mock.test/upload") -> MagicMock:
    """模拟 MinerU get_upload_url 的成功响应"""
    return mock_response(200, {
        "code": 0,
        "data": {"batch_id": batch_id, "file_urls": [upload_url]},
    })

"""测试：mock_helpers 模块"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.mock_helpers import (
    mock_response,
    mock_openai_chunk,
    mock_openai_stream,
    MockPaddlePoller,
    MockMinerUPoller,
    mock_failed_poll,
    mock_timeout_poll,
    make_mineru_zip,
    make_paddleocr_jsonl,
    mock_paddle_submit_response,
    mock_mineru_upload_response,
)


class TestMockResponse:
    def test_basic_json_response(self):
        resp = mock_response(200, {"key": "value"})
        assert resp.status_code == 200
        assert resp.json() == {"key": "value"}
        assert resp.ok is True

    def test_error_response(self):
        resp = mock_response(404, {"error": "not found"})
        assert resp.status_code == 404
        assert resp.ok is False
        assert resp.json()["error"] == "not found"

    def test_binary_content(self):
        resp = mock_response(200, content=b"zip-data")
        assert resp.content == b"zip-data"

    def test_text_response(self):
        resp = mock_response(200, text="line1\nline2")
        assert resp.text == "line1\nline2"


class TestMockOpenAI:
    def test_stream_chunk(self):
        chunk = mock_openai_chunk("Hello")
        assert chunk.choices[0].delta.content == "Hello"

    def test_stream_with_finish(self):
        chunk = mock_openai_chunk("", finish_reason="stop")
        assert chunk.choices[0].finish_reason == "stop"

    def test_stream_iterator(self):
        stream = mock_openai_stream(["Hello", " World", ""])
        texts = [c.choices[0].delta.content for c in stream]
        assert texts == ["Hello", " World", ""]


class TestMockPoller:
    def test_default_paddle_poller(self):
        poller = MockPaddlePoller(total_pages=3)
        r1 = poller.poll().json()["data"]
        r2 = poller.poll().json()["data"]
        r3 = poller.poll().json()["data"]

        assert r1["state"] == "pending"
        assert r2["state"] == "running"
        assert r3["state"] == "done"
        assert r3["resultUrl"]["jsonUrl"] == "https://mock.test/result.jsonl"

    def test_paddle_done_has_start_time(self):
        poller = MockPaddlePoller()
        for _ in range(3):
            resp = poller.poll()
        data = resp.json()["data"]["extractProgress"]
        assert "startTime" in data
        assert "endTime" in data

    def test_custom_sequence(self):
        poller = MockPaddlePoller(sequence=["pending", "pending", "running", "done"])
        states = []
        for _ in range(4):
            states.append(poller.poll().json()["data"]["state"])
        assert states == ["pending", "pending", "running", "done"]

    def test_default_mineru_poller(self):
        poller = MockMinerUPoller()
        r1 = poller.poll().json()
        r2 = poller.poll().json()
        r3 = poller.poll().json()

        assert r1["data"]["extract_result"][0]["state"] == "pending"
        assert r3["data"]["extract_result"][0]["state"] == "done"
        assert r3["data"]["extract_result"][0]["full_zip_url"] == "https://mock.test/result.zip"

    def test_failed_poll(self):
        resp = mock_failed_poll("处理失败")
        data = resp.json()["data"]
        assert data["state"] == "failed"
        assert data["message"] == "处理失败"


class TestMockFileDownloads:
    def test_mineru_zip_with_json(self):
        zip_bytes = make_mineru_zip("# Title\n\nBody.", {"pages": [1]})
        assert len(zip_bytes) > 0

        import zipfile
        from io import BytesIO
        with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
            assert "content/full.md" in zf.namelist()
            assert "content/structure.json" in zf.namelist()

    def test_mineru_zip_without_json(self):
        zip_bytes = make_mineru_zip("Plain text", json_content=None)
        import zipfile
        from io import BytesIO
        with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
            assert "content/structure.json" not in zf.namelist()

    def test_paddleocr_jsonl(self):
        lines = make_paddleocr_jsonl([
            {"layoutParsingResults": [{"markdown": {"text": "Page 1"}}]},
            {"layoutParsingResults": [{"markdown": {"text": "Page 2"}}]},
        ])
        assert "Page 1" in lines
        assert "Page 2" in lines
        assert lines.count("\n") == 1

    def test_mock_submit_response(self):
        resp = mock_paddle_submit_response("job-101")
        assert resp.json()["data"]["jobId"] == "job-101"
        assert resp.status_code == 200

    def test_mock_mineru_upload_response(self):
        resp = mock_mineru_upload_response("batch-101")
        data = resp.json()["data"]
        assert data["batch_id"] == "batch-101"
        assert len(data["file_urls"]) == 1

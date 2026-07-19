# version.py
# VibeOCR 版本信息

__version__ = "4.4.2"
VERSION = __version__

# 版本发布格言（GitHub Release 标题用，英文双引号由工作流拼接）。
# 后续由 publish_release.ps1 / 发布工作流自动从 mottos.json 抽取并回写。
__motto__ = "Discipline is the bridge between goals and accomplishment."

NAME = "VibeOCR"
DESCRIPTION = "智能端到端书籍 OCR 解决方案 — 多模型 AI 驱动，PDF 到纯文本一键提取 | A Smart End-To-End Book OCR solution powered by AI"
URL = "https://github.com/k6G52m4Dz75W/VibeOCR"

def version_info() -> str:
    """返回带名称的版本字符串"""
    return f"{NAME} v{VERSION}"

def version_banner() -> str:
    """返回启动横幅（用于 main() 输出）"""
    return f"{NAME} v{VERSION} — {DESCRIPTION}"

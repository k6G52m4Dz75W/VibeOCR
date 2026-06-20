# version.py
# VibeOCR 版本信息

__version__ = "3.6.0"
VERSION = __version__

NAME = "VibeOCR"
DESCRIPTION = "多模型 OCR 文本提取工具"
URL = "https://github.com/yicki/VibeOCR"

def version_info() -> str:
    """返回带名称的版本字符串"""
    return f"{NAME} v{VERSION}"

def version_banner() -> str:
    """返回启动横幅（用于 main() 输出）"""
    return f"{NAME} v{VERSION} — {DESCRIPTION}"

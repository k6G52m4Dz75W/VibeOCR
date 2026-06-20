# models_config.py
# 模型配置加载器 - 从 TOML 文件加载模型配置
#
# Python 3.11+ 使用内置 tomllib，无需额外依赖
# 支持通过 --config CLI 参数加载外部自定义模型配置（热插拔）

import sys
import os

# Windows GBK 编码下处理 emoji 输出
if sys.platform == "win32" and sys.stdout.encoding and sys.stdout.encoding.lower() in ("gbk", "gb2312"):
    sys.stdout.reconfigure(encoding="utf-8")

try:
    import tomllib
except ImportError:
    tomllib = None
    import importlib.util
    msg = (
        "Python 3.11+ required for TOML support.\n"
        "Run: pip install tomli   # 或升级 Python 到 3.11+"
    )
    print(f"❌ {msg}")
    sys.exit(1)


# 默认配置文件路径（相对于本文件所在目录）
_DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models_config.toml")

# 全局缓存
CONFIGS: dict = {}
DEFAULT_MODEL: str = ""
_loaded_files: list[str] = []


def _load_toml(file_path: str) -> dict:
    """加载单个 TOML 文件并返回模型配置"""
    if not os.path.exists(file_path):
        print(f"⚠️  配置文件不存在: {file_path}")
        return {}

    with open(file_path, "rb") as f:
        data = tomllib.load(f)

    result = {}

    # 解析 [defaults] 段
    global DEFAULT_MODEL
    defaults = data.get("defaults", {})
    if defaults.get("default_model"):
        DEFAULT_MODEL = defaults["default_model"]

    # 解析 [models.*] 段
    models = data.get("models", {})
    for key, cfg in models.items():
        config = dict(cfg)

        if "headers" in config:
            config["headers"] = dict(config["headers"])
        if "payload_template" in config:
            expanded = {}
            _expand_inline_tables(config["payload_template"], expanded)
            config["payload_template"] = expanded

        config.setdefault("prompt", None)
        config.setdefault("note", "")

        result[key] = config

    return result


def _expand_inline_tables(source: dict, target: dict, prefix: str = "") -> None:
    """展开 TOML 的内联表（inline table）为扁平的嵌套 dict"""
    for k, v in source.items():
        if isinstance(v, dict):
            sub = {}
            _expand_inline_tables(v, sub)
            target[k] = sub
        else:
            target[k] = v


def load_configs(config_path: str | None = None) -> dict:
    """
    加载模型配置。

    策略：
    1. 默认加载 `models_config.toml`（内置配置）
    2. 如果指定了 `config_path`（来自 --config），加载并合并（覆盖）
    3. 按加载顺序合并，后加载的覆盖同名字典键
    """
    global CONFIGS, DEFAULT_MODEL, _loaded_files
    _loaded_files = []

    # 1. 加载默认配置
    builtin = _load_toml(_DEFAULT_CONFIG_PATH)
    CONFIGS = dict(builtin)
    _loaded_files.append(_DEFAULT_CONFIG_PATH)

    # 2. 加载外部配置（如果提供）
    if config_path and os.path.exists(config_path):
        external = _load_toml(config_path)
        if external:
            CONFIGS.update(external)
            _loaded_files.append(config_path)
            print(f"📦 已加载外部配置: {config_path}")

    # 3. 如果 TOML 中未指定默认模型，使用内置 fallback
    if not DEFAULT_MODEL:
        DEFAULT_MODEL = "siliconflow_deepseek-ocr"

    # 4. 环境变量覆盖默认模型
    DEFAULT_MODEL = os.environ.get("OCR_MODEL", DEFAULT_MODEL)

    return CONFIGS


# === 模块加载时自动初始化 ===

load_configs()


# 兼容性：如果直接运行 python models_config.py，打印配置概览
if __name__ == "__main__":
    print(f"📂 加载的配置文件: {', '.join(_loaded_files)}")
    print(f"🤖 默认模型: {DEFAULT_MODEL}")
    print(f"📋 共 {len(CONFIGS)} 个模型配置:\n")
    for name, cfg in CONFIGS.items():
        note = f" — {cfg.get('note', '')}" if cfg.get('note') else ""
        print(f"  {name:30s} {cfg['name']}{note}")

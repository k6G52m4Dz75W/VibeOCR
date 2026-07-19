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
PROMPTS: dict = {}          # [prompts] 中的命名提示词库
DEFAULT_MODEL: str = ""
DEFAULT_PROMPT: str = ""    # 模型未显式指定 prompt 时引用的默认提示词
META: dict = {}            # [meta] 元数据提取（utils_extract_meta.py）独立提示词
_loaded_files: list[str] = []


def _load_toml_file(file_path: str) -> dict:
    """加载单个 TOML 文件，返回原始解析字典（不解析 prompt 引用）"""
    if not os.path.exists(file_path):
        print(f"⚠️  配置文件不存在: {file_path}")
        return {}

    with open(file_path, "rb") as f:
        return tomllib.load(f)


def _resolve_prompt(config: dict) -> str | None:
    """
    解析模型最终使用的提示词，优先级：
    1. prompt_ref = "名称"   → 引用 [prompts] 中的命名提示词
    2. prompt_ref = ""        → 显式置空（异步任务模型）
    3. prompt = "..."         → 内联一次性提示词（旧格式兼容）
    4. default_prompt          → 回退到默认命名提示词
    5. 以上皆无               → None
    """
    if "prompt_ref" in config:
        ref = config.pop("prompt_ref")
        if ref == "":
            return None  # 异步任务：显式无 prompt
        if ref not in PROMPTS:
            print(f"⚠️  prompt_ref '{ref}' 未在 [prompts] 中定义，按空 prompt 处理")
            return None
        return PROMPTS[ref]

    # 内联 prompt（兼容旧格式 / 一次性覆盖）
    if "prompt" in config:
        return config["prompt"]

    # 回退到默认提示词
    if DEFAULT_PROMPT:
        return PROMPTS.get(DEFAULT_PROMPT)

    return None


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

    策略（两遍加载）：
    1. 第一遍：收集所有文件中的 [prompts]、[defaults] 与 [meta]，
       构建命名提示词库 PROMPTS、默认模型/默认提示词、元数据提取提示词 META
    2. 第二遍：解析 [models.*]，将 prompt_ref 解析为实际提示词
    3. 内置配置先加载，外部 --config 后加载并覆盖同名项
    """
    global CONFIGS, PROMPTS, DEFAULT_MODEL, DEFAULT_PROMPT, META, _loaded_files
    _loaded_files = []
    PROMPTS = {}
    DEFAULT_MODEL = ""
    DEFAULT_PROMPT = ""
    META = {}

    files = [_DEFAULT_CONFIG_PATH]
    _loaded_files.append(_DEFAULT_CONFIG_PATH)
    if config_path and os.path.exists(config_path):
        files.append(config_path)
        _loaded_files.append(config_path)

    # ---- 第一遍：收集 prompts / defaults ----
    for fp in files:
        data = _load_toml_file(fp)
        defaults = data.get("defaults", {})
        if defaults.get("default_model"):
            DEFAULT_MODEL = defaults["default_model"]
        if defaults.get("default_prompt"):
            DEFAULT_PROMPT = defaults["default_prompt"]
        PROMPTS.update(data.get("prompts", {}))
        META.update(data.get("meta", {}))

    # ---- 第二遍：解析 models ----
    CONFIGS = {}
    for fp in files:
        data = _load_toml_file(fp)
        for key, cfg in data.get("models", {}).items():
            config = dict(cfg)

            if "headers" in config:
                config["headers"] = dict(config["headers"])
            if "payload_template" in config:
                expanded = {}
                _expand_inline_tables(config["payload_template"], expanded)
                config["payload_template"] = expanded

            config["prompt"] = _resolve_prompt(config)
            config.setdefault("note", "")

            CONFIGS[key] = config

    if config_path and os.path.exists(config_path):
        print(f"📦 已加载外部配置: {config_path}")

    # 如果 TOML 中未指定默认模型，使用内置 fallback
    if not DEFAULT_MODEL:
        DEFAULT_MODEL = "siliconflow_deepseek-ocr"

    # 环境变量覆盖默认模型
    DEFAULT_MODEL = os.environ.get("OCR_MODEL", DEFAULT_MODEL)

    return CONFIGS


# === 模块加载时自动初始化 ===

load_configs()


# 兼容性：如果直接运行 python models_config.py，打印配置概览
if __name__ == "__main__":
    print(f"📂 加载的配置文件: {', '.join(_loaded_files)}")
    print(f"🤖 默认模型: {DEFAULT_MODEL}")
    print(f"📝 默认提示词: {DEFAULT_PROMPT or '(无)'}")
    print(f"📚 命名提示词库: {', '.join(PROMPTS.keys()) or '(空)'}")
    print(f"🔧 元数据提取提示词: {', '.join(META.keys()) or '(空)'}")
    print(f"📋 共 {len(CONFIGS)} 个模型配置:\n")
    for name, cfg in CONFIGS.items():
        has_prompt = "✓" if cfg.get("prompt") else "—"
        note = f" — {cfg.get('note', '')}" if cfg.get('note') else ""
        print(f"  {name:30s} {cfg['name']}  [prompt:{has_prompt}]{note}")

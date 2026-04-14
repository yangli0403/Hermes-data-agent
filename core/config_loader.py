"""
配置加载器 — 加载和合并 YAML 配置文件。

负责加载 default.yaml 中的 orbit 配置段，并支持用户通过命令行参数覆盖。
"""

from __future__ import annotations

import copy
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 默认配置
# ---------------------------------------------------------------------------

_DEFAULTS: Dict[str, Any] = {
    "orbit": {
        "model": {
            "generation": "gpt-4.1-mini",
            "semantic_verification": "gpt-4.1-mini",
            "safety_verification": "gpt-4.1-nano",
        },
        "generalization": {
            "num_variants": 5,
            "dimensions": [
                "colloquial",
                "sentence_pattern",
                "param_variation",
                "simplification",
                "driving_scenario",
            ],
        },
        "verification": {
            "semantic_threshold": 0.7,
            "safety_threshold": 0.8,
            "max_length": 50,
            "min_length": 2,
        },
        "processing": {
            "batch_size": 5,
            "max_retries": 3,
            "retry_delay": 1.0,
        },
    }
}


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _deep_merge(base: Dict, override: Dict) -> Dict:
    """递归深度合并两个字典，override 中的值覆盖 base。"""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


# ---------------------------------------------------------------------------
# ConfigLoader
# ---------------------------------------------------------------------------

class ConfigLoader:
    """
    配置加载器。

    公共接口：
      - load(config_path) -> Dict
      - get(key_path, default) -> Any
      - get_orbit_config() -> Dict
    """

    def __init__(self, config_path: Optional[str] = None):
        self._config: Dict[str, Any] = copy.deepcopy(_DEFAULTS)
        self._loaded = False
        if config_path:
            self.load(config_path)

    def load(self, config_path: Optional[str] = None) -> Dict[str, Any]:
        """
        加载配置文件并与默认值合并。

        参数:
            config_path: YAML 配置文件路径。如果为 None，仅使用默认配置。

        返回:
            合并后的完整配置字典

        异常:
            FileNotFoundError: 配置文件不存在
            yaml.YAMLError: YAML 解析错误
        """
        if config_path is None:
            self._loaded = True
            return copy.deepcopy(self._config)

        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_path}")

        with open(path, "r", encoding="utf-8") as f:
            user_config = yaml.safe_load(f) or {}

        self._config = _deep_merge(_DEFAULTS, user_config)
        self._loaded = True
        logger.info("已加载配置文件: %s", config_path)
        return copy.deepcopy(self._config)

    def get(self, key_path: str, default: Any = None) -> Any:
        """
        通过点分路径获取配置值。

        参数:
            key_path: 点分路径，如 "orbit.model.generation"
            default: 默认值

        返回:
            配置值，如果路径不存在则返回默认值
        """
        keys = key_path.split(".")
        current = self._config
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        return current

    def get_orbit_config(self) -> Dict[str, Any]:
        """获取 orbit 配置段的完整内容。"""
        return copy.deepcopy(self._config.get("orbit", {}))

    def override(self, key_path: str, value: Any) -> None:
        """
        通过点分路径覆盖配置值（用于命令行参数覆盖）。

        参数:
            key_path: 点分路径
            value: 新值
        """
        keys = key_path.split(".")
        current = self._config
        for key in keys[:-1]:
            if key not in current or not isinstance(current[key], dict):
                current[key] = {}
            current = current[key]
        current[keys[-1]] = value

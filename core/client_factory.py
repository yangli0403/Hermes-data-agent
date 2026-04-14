"""
模型客户端工厂 — 根据配置统一创建文本、图像与视觉判定客户端。

屏蔽不同 provider 的差异，使业务引擎只依赖工厂接口而非具体客户端实现。
未来新增 provider 时只需扩展工厂映射，无需修改业务逻辑。

公共接口：
  - create_llm_client(config) -> LLMClient
  - create_image_client(config) -> ImageClient
  - create_vlm_client(config) -> VLMClient
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from core.llm_client import LLMClient
from core.image_client import ImageClient
from core.vlm_client import VLMClient

logger = logging.getLogger(__name__)


class ClientFactory:
    """
    模型客户端工厂。

    公共接口：
      - create_llm_client(config) -> LLMClient
      - create_image_client(config) -> ImageClient
      - create_vlm_client(config) -> VLMClient

    配置字典结构：
      {
          "model": "模型名称",
          "max_retries": 3,
          "retry_delay": 1.0,
          "timeout": 120.0,     # 仅 ImageClient
          "max_tokens": 1000,   # 仅 VLMClient
      }
    """

    @staticmethod
    def create_llm_client(config: Optional[Dict[str, Any]] = None) -> LLMClient:
        """
        创建文本生成客户端。

        参数:
            config: 客户端配置字典

        返回:
            LLMClient 实例
        """
        config = config or {}
        return LLMClient(
            model=config.get("model", "gpt-4.1-mini"),
            max_retries=config.get("max_retries", 3),
            retry_delay=config.get("retry_delay", 1.0),
        )

    @staticmethod
    def create_image_client(config: Optional[Dict[str, Any]] = None) -> ImageClient:
        """
        创建图像生成客户端。

        参数:
            config: 客户端配置字典

        返回:
            ImageClient 实例
        """
        config = config or {}
        return ImageClient(
            model=config.get("model", "dall-e-3"),
            max_retries=config.get("max_retries", 3),
            retry_delay=config.get("retry_delay", 2.0),
            timeout=config.get("timeout", 120.0),
        )

    @staticmethod
    def create_vlm_client(config: Optional[Dict[str, Any]] = None) -> VLMClient:
        """
        创建视觉判定客户端。

        参数:
            config: 客户端配置字典

        返回:
            VLMClient 实例
        """
        config = config or {}
        return VLMClient(
            model=config.get("model", "gpt-4.1-mini"),
            max_retries=config.get("max_retries", 3),
            retry_delay=config.get("retry_delay", 1.0),
            max_tokens=config.get("max_tokens", 1000),
        )

"""
图像生成客户端 — 封装文本到图像的生成调用。

负责调用图像生成提供方（如 OpenAI DALL-E、本地 Stable Diffusion 等），
统一处理超时、重试和文件落盘。与 LLMClient 职责分离，避免多模态能力
耦合在单一客户端中。

公共接口：
  - generate(prompt, output_dir, ...) -> ImageResult
  - generate_batch(prompts, output_dir, ...) -> List[ImageResult]
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class ImageResult:
    """图像生成结果。"""

    success: bool = False
    image_path: Optional[str] = None
    prompt: str = ""
    model: str = ""
    resolution: str = ""
    generation_time_ms: int = 0
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return {
            "success": self.success,
            "image_path": self.image_path,
            "prompt": self.prompt,
            "model": self.model,
            "resolution": self.resolution,
            "generation_time_ms": self.generation_time_ms,
            "error": self.error,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# ImageClient
# ---------------------------------------------------------------------------

class ImageClient:
    """
    图像生成客户端。

    公共接口：
      - generate(prompt, output_dir, size, model, quality) -> ImageResult
      - generate_batch(prompts, output_dir, size, model, quality) -> List[ImageResult]

    异常结构：
      - ValueError: 参数不合法（如空 prompt、无效 size）
      - RuntimeError: 重试耗尽后仍然失败
      - FileNotFoundError: 输出目录不存在且无法创建
    """

    # 支持的图像尺寸
    SUPPORTED_SIZES = ["256x256", "512x512", "1024x1024", "1024x1792", "1792x1024"]

    def __init__(
        self,
        model: str = "dall-e-3",
        max_retries: int = 3,
        retry_delay: float = 2.0,
        timeout: float = 120.0,
    ):
        """
        初始化图像生成客户端。

        参数:
            model: 默认图像生成模型名称
            max_retries: 最大重试次数
            retry_delay: 重试间隔基数（秒，指数退避）
            timeout: 单次请求超时（秒）
        """
        self._model = model
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._timeout = timeout
        self._client = None  # 延迟初始化
        self._call_count = 0

    @property
    def call_count(self) -> int:
        """返回累计 API 调用次数。"""
        return self._call_count

    # ---- 公共方法 --------------------------------------------------------

    def generate(
        self,
        prompt: str,
        output_dir: str,
        size: str = "1024x1024",
        model: Optional[str] = None,
        quality: str = "standard",
    ) -> ImageResult:
        """
        根据文本提示词生成单张图像。

        参数:
            prompt: 图像生成提示词
            output_dir: 图像输出目录
            size: 图像尺寸（如 "1024x1024"）
            model: 模型名称（覆盖默认模型）
            quality: 图像质量（"standard" 或 "hd"）

        返回:
            ImageResult 包含生成结果和文件路径

        异常:
            ValueError: prompt 为空或 size 不合法
            RuntimeError: 重试耗尽后仍然失败
        """
        # 参数校验
        if not prompt or not prompt.strip():
            raise ValueError("图像生成提示词不能为空")
        if size not in self.SUPPORTED_SIZES:
            raise ValueError(
                f"不支持的图像尺寸: {size}，支持的尺寸: {self.SUPPORTED_SIZES}"
            )

        use_model = model or self._model
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # 生成唯一文件名
        filename = f"vlm_img_{uuid.uuid4().hex[:8]}.png"
        file_path = output_path / filename

        start_time = time.time()

        try:
            self._call_api_with_retry(
                prompt=prompt,
                file_path=str(file_path),
                size=size,
                model=use_model,
                quality=quality,
            )
            elapsed_ms = int((time.time() - start_time) * 1000)

            return ImageResult(
                success=True,
                image_path=str(file_path),
                prompt=prompt,
                model=use_model,
                resolution=size,
                generation_time_ms=elapsed_ms,
            )
        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.error("图像生成失败: %s", e)
            return ImageResult(
                success=False,
                prompt=prompt,
                model=use_model,
                resolution=size,
                generation_time_ms=elapsed_ms,
                error=str(e),
            )

    def generate_batch(
        self,
        prompts: List[str],
        output_dir: str,
        size: str = "1024x1024",
        model: Optional[str] = None,
        quality: str = "standard",
    ) -> List[ImageResult]:
        """
        批量生成图像。

        参数:
            prompts: 提示词列表
            output_dir: 图像输出目录
            size: 图像尺寸
            model: 模型名称
            quality: 图像质量

        返回:
            ImageResult 列表
        """
        results = []
        for i, prompt in enumerate(prompts):
            logger.info("图像生成进度: %d/%d", i + 1, len(prompts))
            result = self.generate(
                prompt=prompt,
                output_dir=output_dir,
                size=size,
                model=model,
                quality=quality,
            )
            results.append(result)
        return results

    # ---- 内部方法 --------------------------------------------------------

    def _get_client(self):
        """延迟初始化 OpenAI 客户端。"""
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI()
        return self._client

    def _call_api_with_retry(
        self,
        prompt: str,
        file_path: str,
        size: str,
        model: str,
        quality: str,
    ) -> None:
        """
        带重试的图像生成 API 调用（指数退避）。

        生成成功后将图像写入 file_path。
        """
        import base64

        client = self._get_client()
        last_error: Optional[Exception] = None

        for attempt in range(1, self._max_retries + 1):
            try:
                response = client.images.generate(
                    model=model,
                    prompt=prompt,
                    size=size,
                    quality=quality,
                    n=1,
                    response_format="b64_json",
                )
                self._call_count += 1

                # 解码并保存图像
                image_data = base64.b64decode(response.data[0].b64_json)
                with open(file_path, "wb") as f:
                    f.write(image_data)

                logger.debug(
                    "图像生成成功 (model=%s, attempt=%d, path=%s)",
                    model, attempt, file_path,
                )
                return

            except Exception as e:
                last_error = e
                wait = self._retry_delay * (2 ** (attempt - 1))
                logger.warning(
                    "图像生成失败 (attempt=%d/%d, model=%s): %s — 等待 %.1fs 后重试",
                    attempt, self._max_retries, model, e, wait,
                )
                time.sleep(wait)

        raise RuntimeError(
            f"图像生成在 {self._max_retries} 次重试后仍然失败: {last_error}"
        )

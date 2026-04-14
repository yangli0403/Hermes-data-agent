"""
图像合成协调器 — 协调图像生成并将结果写回 VLMSample。

依据 VLMSample 中的 image_prompt 调用 ImageClient 生成图像文件，
产出图像文件路径、生成参数和异常信息，并更新样本状态。

公共接口：
  - synthesize(sample, output_dir) -> VLMSample
  - synthesize_batch(samples, output_dir) -> List[VLMSample]
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

from core.contracts import VLMSample
from core.image_client import ImageClient, ImageResult

logger = logging.getLogger(__name__)


class ImageSynthesisCoordinator:
    """
    图像合成协调器。

    公共接口：
      - synthesize(sample, output_dir) -> VLMSample
      - synthesize_batch(samples, output_dir) -> List[VLMSample]

    异常结构：
      - ValueError: 样本缺少 image_prompt
    """

    def __init__(
        self,
        image_client: Optional[ImageClient] = None,
        default_size: str = "1024x1024",
        default_quality: str = "standard",
    ):
        """
        初始化图像合成协调器。

        参数:
            image_client: 图像生成客户端
            default_size: 默认图像尺寸
            default_quality: 默认图像质量
        """
        self._image_client = image_client or ImageClient()
        self._default_size = default_size
        self._default_quality = default_quality

    def synthesize(
        self,
        sample: VLMSample,
        output_dir: str,
    ) -> VLMSample:
        """
        为单个 VLMSample 生成图像。

        生成成功后更新 sample 的 image_path、image_metadata 和 status；
        生成失败则标记 status 为 "failed" 并记录 failure_reason。

        参数:
            sample: 候选样本（必须包含 image_prompt）
            output_dir: 图像输出目录

        返回:
            更新后的 VLMSample（原地修改并返回）

        异常:
            ValueError: 样本缺少 image_prompt
        """
        if not sample.image_prompt:
            raise ValueError(
                f"样本 {sample.sample_id} 缺少 image_prompt，无法生成图像"
            )

        # 确保输出目录存在
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        result: ImageResult = self._image_client.generate(
            prompt=sample.image_prompt,
            output_dir=output_dir,
            size=self._default_size,
            quality=self._default_quality,
        )

        if result.success:
            sample.image_path = result.image_path
            sample.image_metadata = {
                "model": result.model,
                "resolution": result.resolution,
                "generation_time_ms": result.generation_time_ms,
            }
            sample.image_generation_model = result.model
            sample.status = "image_generated"
            logger.debug(
                "图像生成成功: sample=%s, path=%s",
                sample.sample_id, result.image_path,
            )
        else:
            sample.status = "failed"
            sample.failure_reason = f"图像生成失败: {result.error}"
            logger.warning(
                "图像生成失败: sample=%s, error=%s",
                sample.sample_id, result.error,
            )

        return sample

    def synthesize_batch(
        self,
        samples: List[VLMSample],
        output_dir: str,
    ) -> List[VLMSample]:
        """
        批量为 VLMSample 生成图像。

        跳过已失败或已有图像的样本。

        参数:
            samples: 候选样本列表
            output_dir: 图像输出目录

        返回:
            更新后的 VLMSample 列表
        """
        results: List[VLMSample] = []
        for i, sample in enumerate(samples):
            logger.info("图像合成进度: %d/%d", i + 1, len(samples))

            # 跳过已失败或已有图像的样本
            if sample.status == "failed":
                logger.debug("跳过已失败样本: %s", sample.sample_id)
                results.append(sample)
                continue
            if sample.has_image:
                logger.debug("跳过已有图像的样本: %s", sample.sample_id)
                results.append(sample)
                continue

            updated = self.synthesize(sample, output_dir)
            results.append(updated)

        succeeded = sum(1 for s in results if s.status == "image_generated")
        failed = sum(1 for s in results if s.status == "failed")
        logger.info(
            "图像合成完成: 成功=%d, 失败=%d, 总计=%d",
            succeeded, failed, len(results),
        )
        return results

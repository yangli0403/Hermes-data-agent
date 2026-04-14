"""
图像内容一致性校验器 — 对 VLMSample 的图像与文本执行视觉一致性校验。

调用 VLMClient 判断生成的图像是否与问答对和语义陈述一致。
这是验证链的最后一层，需要消耗多模态 API 成本。

公共接口：
  - verify(sample, threshold) -> StageResult
  - verify_batch(samples, threshold) -> List[StageResult]
"""

from __future__ import annotations

import logging
from typing import List, Optional

from core.contracts import VLMSample
from core.vlm_client import VLMClient, VLMJudgment
from core.rule_verifier import StageResult

logger = logging.getLogger(__name__)


class VisionConsistencyVerifier:
    """
    图像内容一致性校验器。

    公共接口：
      - verify(sample, threshold) -> StageResult
      - verify_batch(samples, threshold) -> List[StageResult]

    异常结构：
      - FileNotFoundError: 图像文件不存在（内部捕获）
      - RuntimeError: VLM 调用失败（内部捕获）
    """

    def __init__(
        self,
        vlm_client: Optional[VLMClient] = None,
        model: str = "gpt-4.1-mini",
        default_threshold: float = 0.7,
    ):
        """
        初始化图像内容一致性校验器。

        参数:
            vlm_client: VLM 客户端
            model: 默认模型名称
            default_threshold: 默认通过阈值
        """
        self._vlm = vlm_client or VLMClient(model=model)
        self._default_threshold = default_threshold

    def verify(
        self,
        sample: VLMSample,
        threshold: Optional[float] = None,
    ) -> StageResult:
        """
        对单个 VLMSample 执行图像内容一致性校验。

        校验步骤：
          1. 检查图像文件是否存在
          2. 调用 VLMClient 判断图像与问答对的一致性
          3. 调用 VLMClient 判断图像与语义陈述的一致性
          4. 综合两项判定结果

        参数:
            sample: 待校验的候选样本
            threshold: 通过阈值

        返回:
            StageResult 校验结果
        """
        use_threshold = threshold or self._default_threshold

        # 前置检查：图像必须已生成
        if not sample.has_image:
            return StageResult(
                stage="vision_consistency",
                passed=False,
                score=0.0,
                reason="样本尚未生成图像，无法执行视觉一致性校验",
            )

        try:
            # 1. 判断图像与问答对的一致性
            qa_judgment = self._vlm.judge(
                image_path=sample.image_path,
                question=sample.question,
                expected_answer=sample.answer,
                threshold=use_threshold,
            )

            # 2. 判断图像与语义陈述的一致性
            statement_judgment = self._vlm.judge_consistency(
                image_path=sample.image_path,
                statement=sample.statement,
                threshold=use_threshold,
            )

            # 3. 综合评分（加权平均：QA 60%，陈述 40%）
            combined_score = (
                qa_judgment.score * 0.6 + statement_judgment.score * 0.4
            )
            combined_passed = combined_score >= use_threshold

            reason_parts = []
            reason_parts.append(
                f"QA一致性: {qa_judgment.score:.2f} "
                f"({'通过' if qa_judgment.passed else '未通过'}) — {qa_judgment.reason}"
            )
            reason_parts.append(
                f"陈述一致性: {statement_judgment.score:.2f} "
                f"({'通过' if statement_judgment.passed else '未通过'}) — {statement_judgment.reason}"
            )
            reason_parts.append(
                f"综合分数: {combined_score:.2f} "
                f"({'通过' if combined_passed else '未通过'})"
            )

            return StageResult(
                stage="vision_consistency",
                passed=combined_passed,
                score=combined_score,
                reason=" | ".join(reason_parts),
            )

        except FileNotFoundError as e:
            logger.error("图像文件不存在: %s", e)
            return StageResult(
                stage="vision_consistency",
                passed=False,
                score=0.0,
                reason=f"图像文件不存在: {e}",
            )
        except Exception as e:
            logger.error("视觉一致性校验失败: %s", e)
            return StageResult(
                stage="vision_consistency",
                passed=False,
                score=0.0,
                reason=f"VLM 调用失败: {e}",
            )

    def verify_batch(
        self,
        samples: List[VLMSample],
        threshold: Optional[float] = None,
    ) -> List[StageResult]:
        """
        批量图像内容一致性校验。

        参数:
            samples: 样本列表
            threshold: 通过阈值

        返回:
            StageResult 列表
        """
        results = []
        for i, sample in enumerate(samples):
            logger.info("视觉一致性校验进度: %d/%d", i + 1, len(samples))
            result = self.verify(sample, threshold)
            results.append(result)
        return results

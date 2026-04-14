"""
VLM 管线编排器 — 编排视觉链路的完整流程。

负责串联种子引擎、泛化引擎、图像合成、三层验证和导出的完整流程。
提供单图最小闭环和批量运行两种模式。

公共接口：
  - run_single(seed, output_dir, run_id) -> PipelineResult
  - run_batch(seeds, output_dir, run_id) -> BatchPipelineResult
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.contracts import VisualSeed, VLMSample, VLMRecord, LabelQuality
from core.visual_generalization_engine import VisualGeneralizationEngine
from core.image_synthesis_coordinator import ImageSynthesisCoordinator
from core.schema_verifier import SchemaVerifier
from core.consistency_verifier import ConsistencyVerifier
from core.vision_consistency_verifier import VisionConsistencyVerifier
from core.provenance_tracker import ProvenanceTracker
from core.rule_verifier import StageResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 管线结果数据结构
# ---------------------------------------------------------------------------

@dataclass
class PipelineResult:
    """单个种子的管线执行结果。"""

    seed_id: str = ""
    samples: List[VLMSample] = field(default_factory=list)
    records: List[VLMRecord] = field(default_factory=list)
    total_generated: int = 0
    total_verified: int = 0
    total_rejected: int = 0
    total_failed: int = 0
    elapsed_ms: int = 0
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return {
            "seed_id": self.seed_id,
            "total_generated": self.total_generated,
            "total_verified": self.total_verified,
            "total_rejected": self.total_rejected,
            "total_failed": self.total_failed,
            "elapsed_ms": self.elapsed_ms,
            "errors": self.errors,
            "records": [r.to_dict() for r in self.records],
        }


@dataclass
class BatchPipelineResult:
    """批量管线执行结果。"""

    run_id: str = ""
    results: List[PipelineResult] = field(default_factory=list)
    total_seeds: int = 0
    total_records: int = 0
    total_verified: int = 0
    total_rejected: int = 0
    total_failed: int = 0
    elapsed_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return {
            "run_id": self.run_id,
            "total_seeds": self.total_seeds,
            "total_records": self.total_records,
            "total_verified": self.total_verified,
            "total_rejected": self.total_rejected,
            "total_failed": self.total_failed,
            "elapsed_ms": self.elapsed_ms,
        }


# ---------------------------------------------------------------------------
# VLM Pipeline Runner
# ---------------------------------------------------------------------------

class VLMPipelineRunner:
    """
    VLM 管线编排器。

    公共接口：
      - run_single(seed, output_dir, run_id, samples_per_seed) -> PipelineResult
      - run_batch(seeds, output_dir, run_id, samples_per_seed) -> BatchPipelineResult

    管线阶段：
      1. 文本泛化（VisualGeneralizationEngine）
      2. 图像合成（ImageSynthesisCoordinator）
      3. 结构校验（SchemaVerifier）
      4. 文本自洽校验（ConsistencyVerifier）
      5. 视觉一致性校验（VisionConsistencyVerifier）
      6. 记录映射（VLMSample → VLMRecord）
    """

    def __init__(
        self,
        generalization_engine: Optional[VisualGeneralizationEngine] = None,
        image_coordinator: Optional[ImageSynthesisCoordinator] = None,
        schema_verifier: Optional[SchemaVerifier] = None,
        consistency_verifier: Optional[ConsistencyVerifier] = None,
        vision_verifier: Optional[VisionConsistencyVerifier] = None,
        provenance_tracker: Optional[ProvenanceTracker] = None,
        pass_threshold: float = 0.7,
    ):
        """
        初始化管线编排器。

        参数:
            generalization_engine: 视觉泛化引擎
            image_coordinator: 图像合成协调器
            schema_verifier: 结构校验器
            consistency_verifier: 文本自洽校验器
            vision_verifier: 视觉一致性校验器
            provenance_tracker: 来源链追踪器
            pass_threshold: 验证通过阈值
        """
        self._gen_engine = generalization_engine or VisualGeneralizationEngine()
        self._img_coordinator = image_coordinator or ImageSynthesisCoordinator()
        self._schema_verifier = schema_verifier or SchemaVerifier()
        self._consistency_verifier = consistency_verifier or ConsistencyVerifier()
        self._vision_verifier = vision_verifier or VisionConsistencyVerifier()
        self._tracker = provenance_tracker
        self._pass_threshold = pass_threshold

    def run_single(
        self,
        seed: VisualSeed,
        output_dir: str,
        run_id: str = "",
        samples_per_seed: int = 1,
    ) -> PipelineResult:
        """
        对单个种子执行完整管线。

        参数:
            seed: 视觉任务种子
            output_dir: 输出目录
            run_id: 运行批次标识
            samples_per_seed: 每个种子生成的样本数量

        返回:
            PipelineResult 管线执行结果
        """
        if not run_id:
            run_id = f"vlm_run_{uuid.uuid4().hex[:8]}"

        start_time = time.time()
        result = PipelineResult(seed_id=seed.seed_id)

        # 阶段 1: 文本泛化
        try:
            samples = self._gen_engine.generate(seed, count=samples_per_seed)
            result.total_generated = len(samples)
        except Exception as e:
            result.errors.append(f"文本泛化失败: {e}")
            result.elapsed_ms = int((time.time() - start_time) * 1000)
            return result

        # 阶段 2: 图像合成
        image_dir = f"{output_dir}/images"
        samples = self._img_coordinator.synthesize_batch(samples, image_dir)

        # 阶段 3-5: 三层验证
        for sample in samples:
            if sample.status == "failed":
                result.total_failed += 1
                continue

            verification_results = []

            # 3. 结构校验
            schema_result = self._schema_verifier.verify(sample)
            verification_results.append(schema_result.to_dict())
            if not schema_result.passed:
                sample.status = "rejected"
                sample.failure_reason = schema_result.reason
                sample.verification_results = verification_results
                result.total_rejected += 1
                continue

            # 4. 文本自洽校验
            consistency_result = self._consistency_verifier.verify(
                sample, self._pass_threshold
            )
            verification_results.append(consistency_result.to_dict())
            if not consistency_result.passed:
                sample.status = "rejected"
                sample.failure_reason = consistency_result.reason
                sample.verification_results = verification_results
                result.total_rejected += 1
                continue

            # 5. 视觉一致性校验（仅对有图像的样本）
            if sample.has_image:
                vision_result = self._vision_verifier.verify(
                    sample, self._pass_threshold
                )
                verification_results.append(vision_result.to_dict())
                if not vision_result.passed:
                    sample.status = "rejected"
                    sample.failure_reason = vision_result.reason
                    sample.verification_results = verification_results
                    result.total_rejected += 1
                    continue

            # 全部通过
            sample.status = "verified"
            sample.verification_results = verification_results
            result.total_verified += 1

        # 阶段 6: 记录映射
        for sample in samples:
            if sample.is_verified:
                # 计算综合置信度
                scores = [
                    vr.get("score", 0.0)
                    for vr in sample.verification_results
                    if isinstance(vr, dict)
                ]
                confidence = sum(scores) / len(scores) if scores else 0.0

                record = VLMRecord.from_sample(
                    sample=sample,
                    seed=seed,
                    run_id=run_id,
                    confidence_score=confidence,
                )
                result.records.append(record)

        result.samples = samples
        result.elapsed_ms = int((time.time() - start_time) * 1000)

        logger.info(
            "管线完成: seed=%s, 生成=%d, 通过=%d, 拒绝=%d, 失败=%d, 耗时=%dms",
            seed.seed_id,
            result.total_generated,
            result.total_verified,
            result.total_rejected,
            result.total_failed,
            result.elapsed_ms,
        )
        return result

    def run_batch(
        self,
        seeds: List[VisualSeed],
        output_dir: str,
        run_id: str = "",
        samples_per_seed: int = 1,
    ) -> BatchPipelineResult:
        """
        批量执行管线。

        参数:
            seeds: 种子列表
            output_dir: 输出目录
            run_id: 运行批次标识
            samples_per_seed: 每个种子生成的样本数量

        返回:
            BatchPipelineResult 批量执行结果
        """
        if not run_id:
            run_id = f"vlm_batch_{uuid.uuid4().hex[:8]}"

        start_time = time.time()
        batch_result = BatchPipelineResult(
            run_id=run_id,
            total_seeds=len(seeds),
        )

        for i, seed in enumerate(seeds):
            logger.info("批量管线进度: %d/%d", i + 1, len(seeds))
            result = self.run_single(
                seed=seed,
                output_dir=output_dir,
                run_id=run_id,
                samples_per_seed=samples_per_seed,
            )
            batch_result.results.append(result)
            batch_result.total_records += len(result.records)
            batch_result.total_verified += result.total_verified
            batch_result.total_rejected += result.total_rejected
            batch_result.total_failed += result.total_failed

        batch_result.elapsed_ms = int((time.time() - start_time) * 1000)

        logger.info(
            "批量管线完成: run_id=%s, 种子=%d, 记录=%d, 通过=%d, 拒绝=%d, 失败=%d",
            run_id,
            batch_result.total_seeds,
            batch_result.total_records,
            batch_result.total_verified,
            batch_result.total_rejected,
            batch_result.total_failed,
        )
        return batch_result

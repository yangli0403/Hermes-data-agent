"""
视觉泛化引擎 — 从 VisualSeed 生成候选 VLMSample。

基于每个 VisualSeed 调用 LLMClient 生成文本部分，形成候选样本，
包含 question、answer、image_prompt、statement 和基础元数据。

公共接口：
  - generate(seed, count) -> List[VLMSample]
  - generate_batch(seeds, count) -> List[VLMSample]
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from core.contracts import VisualSeed, VLMSample
from core.llm_client import LLMClient
from core.provenance_tracker import ProvenanceTracker

logger = logging.getLogger(__name__)


class VisualGeneralizationEngine:
    """
    视觉泛化引擎。

    公共接口：
      - generate(seed, count) -> List[VLMSample]
      - generate_batch(seeds, count) -> List[VLMSample]

    异常结构：
      - ValueError: 种子对象不合法
      - RuntimeError: LLM 调用失败
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        provenance_tracker: Optional[ProvenanceTracker] = None,
        model: str = "gpt-4.1-mini",
    ):
        """
        初始化视觉泛化引擎。

        参数:
            llm_client: LLM 客户端实例
            provenance_tracker: 来源链追踪器
            model: 默认模型名称
        """
        self._llm = llm_client or LLMClient(model=model)
        self._tracker = provenance_tracker
        self._model = model

    def generate(
        self,
        seed: VisualSeed,
        count: int = 1,
    ) -> List[VLMSample]:
        """
        从单个 VisualSeed 生成候选 VLMSample 列表。

        参数:
            seed: 视觉任务种子
            count: 生成样本数量

        返回:
            VLMSample 列表

        异常:
            ValueError: 种子对象不合法
            RuntimeError: LLM 调用失败
        """
        if not seed.scene_description:
            raise ValueError("种子的场景描述不能为空")

        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(seed, count)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        raw_response = self._llm.chat_json(messages, model=self._model)
        samples = self._parse_response(raw_response, seed)

        # 记录到追踪器
        if self._tracker:
            for sample in samples:
                self._tracker.record_generalization(
                    seed=None,  # VisualSeed 不是 Seed 类型，追踪器需要扩展
                    variants=[sample.question],
                    metadata={
                        "vlm_seed_id": seed.seed_id,
                        "generation_model": self._model,
                        "sample_id": sample.sample_id,
                    },
                )

        logger.info(
            "从种子 %s 生成 %d 个候选样本",
            seed.seed_id, len(samples),
        )
        return samples

    def generate_batch(
        self,
        seeds: List[VisualSeed],
        count: int = 1,
    ) -> List[VLMSample]:
        """
        批量生成候选样本。

        参数:
            seeds: 种子列表
            count: 每个种子生成的样本数量

        返回:
            所有生成的 VLMSample 列表
        """
        all_samples: List[VLMSample] = []
        for i, seed in enumerate(seeds):
            logger.info("视觉泛化进度: %d/%d", i + 1, len(seeds))
            try:
                samples = self.generate(seed, count)
                all_samples.extend(samples)
            except Exception as e:
                logger.error("种子 %s 生成失败: %s", seed.seed_id, e)
                # 生成失败的样本也记录
                failed_sample = VLMSample(
                    seed_id=seed.seed_id,
                    status="failed",
                    failure_reason=str(e),
                )
                all_samples.append(failed_sample)
        return all_samples

    # ---- 内部方法 --------------------------------------------------------

    def _build_system_prompt(self) -> str:
        """构建系统提示词。"""
        return (
            "你是一个视觉问答数据生成专家。你的任务是根据给定的场景描述和约束条件，"
            "生成高质量的视觉问答样本。每个样本必须包含：\n"
            "1. question: 针对场景的视觉问题\n"
            "2. answer: 问题的准确答案\n"
            "3. image_prompt: 用于图像生成的详细提示词（英文）\n"
            "4. statement: 用于一致性校验的语义陈述\n\n"
            "请以 JSON 格式返回结果，包含一个 'samples' 数组。"
        )

    def _build_user_prompt(self, seed: VisualSeed, count: int) -> str:
        """构建用户提示词。"""
        entities_str = "、".join(seed.entities) if seed.entities else "无特定实体"
        constraints_str = json.dumps(seed.constraints, ensure_ascii=False) if seed.constraints else "无"

        return (
            f"请生成 {count} 个视觉问答样本。\n\n"
            f"场景描述：{seed.scene_description}\n"
            f"任务类别：{seed.task_category}\n"
            f"场景实体：{entities_str}\n"
            f"问题类型：{seed.question_type}\n"
            f"答案风格：{seed.answer_style}\n"
            f"图像风格：{seed.image_style}\n"
            f"约束条件：{constraints_str}\n\n"
            f"请确保 image_prompt 使用英文，且足够详细以指导图像生成。"
        )

    def _parse_response(
        self,
        response: Dict[str, Any],
        seed: VisualSeed,
    ) -> List[VLMSample]:
        """解析 LLM 响应为 VLMSample 列表。"""
        samples_data = response.get("samples", [])
        if not samples_data and isinstance(response.get("items"), list):
            samples_data = response["items"]

        samples: List[VLMSample] = []
        for item in samples_data:
            sample = VLMSample(
                seed_id=seed.seed_id,
                question=item.get("question", ""),
                answer=item.get("answer", ""),
                image_prompt=item.get("image_prompt", ""),
                statement=item.get("statement", ""),
                generation_model=self._model,
                status="pending",
                metadata={
                    "task_category": seed.task_category,
                    "question_type": seed.question_type,
                },
            )
            samples.append(sample)

        return samples

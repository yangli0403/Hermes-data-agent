"""
VLM 数据契约 — 定义视觉链路的核心数据结构。

本模块包含视觉链路中所有共享的数据对象：
  - BaseRecord：公共基础元数据载体
  - VisualSeed：视觉任务种子
  - VLMSample：视觉链路中间态候选样本
  - VLMRecord：视觉链路最终输出记录

设计原则：
  1. 文本 ORBIT 与视觉 VLM 不共享业务对象本身，但共享公共元数据字段
  2. VLMSample 作为中间态，承载生成、验证、失败回溯的完整信息
  3. VLMRecord 作为最终输出态，面向训练与审阅导出
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# 枚举类型
# ---------------------------------------------------------------------------

class LabelQuality(str, Enum):
    """质量标签枚举。"""
    VERIFIED = "synthetic_verified"
    REJECTED = "synthetic_rejected"
    PENDING = "pending_verification"
    FAILED_GENERATION = "failed_generation"


class QuestionType(str, Enum):
    """视觉问答的问题类型枚举。"""
    DESCRIPTIVE = "descriptive"          # 描述性问题（描述图中内容）
    COUNTING = "counting"                # 计数类问题
    SPATIAL = "spatial"                  # 空间关系问题
    COMPARATIVE = "comparative"          # 比较类问题
    REASONING = "reasoning"              # 推理类问题
    YES_NO = "yes_no"                    # 是非判断问题
    IDENTIFICATION = "identification"    # 识别类问题


# ---------------------------------------------------------------------------
# BaseRecord — 公共基础元数据载体
# ---------------------------------------------------------------------------

@dataclass
class BaseRecord:
    """
    公共基础元数据载体。

    文本 OrbitRecord 与视觉 VLMRecord 共享的元数据字段。
    当前阶段不修改 OrbitRecord 的继承关系，仅作为设计契约
    供后续统一重构时使用。

    字段说明：
      - record_id: 全局唯一记录标识
      - run_id: 本次运行的批次标识
      - source_chain: 来源链（种子来源、模板版本等）
      - verification_chain: 验证链（各阶段验证结果列表）
      - label_quality: 质量标签
      - created_at: 记录创建时间（ISO 8601）
    """

    record_id: str = ""
    run_id: str = ""
    source_chain: Dict[str, Any] = field(default_factory=dict)
    verification_chain: List[Dict[str, Any]] = field(default_factory=list)
    label_quality: str = LabelQuality.PENDING.value
    created_at: str = ""

    def __post_init__(self):
        if not self.record_id:
            self.record_id = f"rec_{uuid.uuid4().hex[:12]}"
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return asdict(self)


# ---------------------------------------------------------------------------
# VisualSeed — 视觉任务种子
# ---------------------------------------------------------------------------

@dataclass
class VisualSeed:
    """
    视觉任务种子 — 视觉链路的最小处理单元。

    每个种子描述一个受控视觉任务，包含场景类别、实体约束、
    问题类型、回答目标和图像提示前置条件。

    字段说明：
      - seed_id: 种子唯一标识
      - task_category: 任务类别（如 "scene_understanding"、"object_recognition"）
      - scene_description: 场景描述文本
      - entities: 场景中应包含的实体列表
      - question_type: 问题类型（QuestionType 枚举值）
      - answer_style: 答案风格（如 "brief"、"detailed"、"structured"）
      - constraints: 额外约束条件字典
      - image_style: 图像风格要求（如 "photorealistic"、"illustration"）
      - source_config: 来源配置文件路径
      - metadata: 扩展元数据
    """

    seed_id: str = ""
    task_category: str = ""
    scene_description: str = ""
    entities: List[str] = field(default_factory=list)
    question_type: str = QuestionType.DESCRIPTIVE.value
    answer_style: str = "brief"
    constraints: Dict[str, Any] = field(default_factory=dict)
    image_style: str = "photorealistic"
    source_config: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.seed_id:
            self.seed_id = f"vseed_{uuid.uuid4().hex[:8]}"

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VisualSeed":
        """从字典创建 VisualSeed 对象。"""
        return cls(
            seed_id=data.get("seed_id", ""),
            task_category=data.get("task_category", ""),
            scene_description=data.get("scene_description", ""),
            entities=data.get("entities", []),
            question_type=data.get("question_type", QuestionType.DESCRIPTIVE.value),
            answer_style=data.get("answer_style", "brief"),
            constraints=data.get("constraints", {}),
            image_style=data.get("image_style", "photorealistic"),
            source_config=data.get("source_config", ""),
            metadata=data.get("metadata", {}),
        )


# ---------------------------------------------------------------------------
# VLMSample — 视觉链路中间态候选样本
# ---------------------------------------------------------------------------

@dataclass
class VLMSample:
    """
    视觉链路中间态候选样本。

    在验证通过后映射为 VLMRecord。承载"问题—答案—图像提示词—
    图像产物—验证轨迹"的完整生命周期信息。

    字段说明：
      - sample_id: 样本唯一标识
      - seed_id: 来源种子标识
      - question: 视觉问答的问题文本
      - answer: 视觉问答的答案文本
      - image_prompt: 用于图像生成的提示词
      - statement: 语义陈述（用于一致性校验的参考文本）
      - image_path: 生成的图像文件路径（生成后填充）
      - image_metadata: 图像生成元数据（分辨率、模型、耗时等）
      - generation_model: 文本生成使用的模型名称
      - image_generation_model: 图像生成使用的模型名称
      - verification_results: 各阶段验证结果列表
      - status: 样本当前状态
      - failure_reason: 失败原因（如有）
      - metadata: 扩展元数据
      - created_at: 创建时间
    """

    sample_id: str = ""
    seed_id: str = ""
    question: str = ""
    answer: str = ""
    image_prompt: str = ""
    statement: str = ""
    image_path: Optional[str] = None
    image_metadata: Dict[str, Any] = field(default_factory=dict)
    generation_model: str = ""
    image_generation_model: str = ""
    verification_results: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "pending"  # pending | image_generated | verified | rejected | failed
    failure_reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def __post_init__(self):
        if not self.sample_id:
            self.sample_id = f"vsample_{uuid.uuid4().hex[:8]}"
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VLMSample":
        """从字典创建 VLMSample 对象。"""
        return cls(
            sample_id=data.get("sample_id", ""),
            seed_id=data.get("seed_id", ""),
            question=data.get("question", ""),
            answer=data.get("answer", ""),
            image_prompt=data.get("image_prompt", ""),
            statement=data.get("statement", ""),
            image_path=data.get("image_path"),
            image_metadata=data.get("image_metadata", {}),
            generation_model=data.get("generation_model", ""),
            image_generation_model=data.get("image_generation_model", ""),
            verification_results=data.get("verification_results", []),
            status=data.get("status", "pending"),
            failure_reason=data.get("failure_reason"),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", ""),
        )

    @property
    def is_verified(self) -> bool:
        """样本是否已通过全部验证。"""
        return self.status == "verified"

    @property
    def has_image(self) -> bool:
        """样本是否已生成图像。"""
        return self.image_path is not None and self.image_path != ""


# ---------------------------------------------------------------------------
# VLMRecord — 视觉链路最终输出记录
# ---------------------------------------------------------------------------

@dataclass
class VLMRecord:
    """
    视觉链路最终输出记录。

    面向训练与审阅导出。训练导出使用 messages + images 字段；
    审阅导出额外使用 review_fields 字段。

    字段说明：
      - record_id: 全局唯一记录标识
      - run_id: 本次运行的批次标识
      - messages: 训练格式的对话消息列表（OpenAI 格式）
      - images: 关联的图像路径列表
      - source_chain: 来源链
      - verification_chain: 验证链
      - confidence_score: 综合置信度分数
      - label_quality: 质量标签
      - review_fields: 审阅专用字段（提示词、失败原因、模型版本等）
      - created_at: 记录创建时间
    """

    record_id: str = ""
    run_id: str = ""
    messages: List[Dict[str, Any]] = field(default_factory=list)
    images: List[str] = field(default_factory=list)
    source_chain: Dict[str, Any] = field(default_factory=dict)
    verification_chain: List[Dict[str, Any]] = field(default_factory=list)
    confidence_score: float = 0.0
    label_quality: str = LabelQuality.PENDING.value
    review_fields: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def __post_init__(self):
        if not self.record_id:
            self.record_id = f"vlm_{uuid.uuid4().hex[:12]}"
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return asdict(self)

    @classmethod
    def from_sample(
        cls,
        sample: VLMSample,
        seed: VisualSeed,
        run_id: str = "",
        confidence_score: float = 0.0,
    ) -> "VLMRecord":
        """
        从 VLMSample 构建最终输出记录。

        参数:
            sample: 已验证的候选样本
            seed: 来源种子
            run_id: 运行批次标识
            confidence_score: 综合置信度

        返回:
            VLMRecord 实例
        """
        # 构建 OpenAI 格式的训练消息
        messages = [
            {"role": "user", "content": sample.question},
            {"role": "assistant", "content": sample.answer},
        ]

        # 构建来源链
        source_chain = {
            "seed_id": seed.seed_id,
            "task_category": seed.task_category,
            "scene_description": seed.scene_description,
            "entities": seed.entities,
            "question_type": seed.question_type,
            "source_config": seed.source_config,
        }

        # 构建审阅字段
        review_fields = {
            "image_prompt": sample.image_prompt,
            "statement": sample.statement,
            "generation_model": sample.generation_model,
            "image_generation_model": sample.image_generation_model,
            "failure_reason": sample.failure_reason,
            "sample_status": sample.status,
        }

        # 确定质量标签
        label = (
            LabelQuality.VERIFIED.value
            if sample.is_verified
            else LabelQuality.REJECTED.value
        )

        return cls(
            run_id=run_id,
            messages=messages,
            images=[sample.image_path] if sample.image_path else [],
            source_chain=source_chain,
            verification_chain=sample.verification_results,
            confidence_score=confidence_score,
            label_quality=label,
            review_fields=review_fields,
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VLMRecord":
        """从字典创建 VLMRecord 对象。"""
        return cls(
            record_id=data.get("record_id", ""),
            run_id=data.get("run_id", ""),
            messages=data.get("messages", []),
            images=data.get("images", []),
            source_chain=data.get("source_chain", {}),
            verification_chain=data.get("verification_chain", []),
            confidence_score=data.get("confidence_score", 0.0),
            label_quality=data.get("label_quality", LabelQuality.PENDING.value),
            review_fields=data.get("review_fields", {}),
            created_at=data.get("created_at", ""),
        )

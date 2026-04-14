"""
来源链与验证链追踪器 — 记录每条数据的完整生命周期。

ORBIT 的核心精髓之一是"可追溯性"。本模块为每条生成的变体记录：
  1. 来源链（source_chain）— 来自哪个种子、哪个领域、哪些参数
  2. 验证链（verification_chain）— 每层验证的结果和原因
  3. 生成元数据 — 使用的模型、维度、时间戳

所有记录持久化为 JSONL 格式的轨迹文件。
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.seed_engine import Seed

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class OrbitRecord:
    """最终输出记录 — 包含完整的来源链和验证链。"""

    record_id: str
    standard_utterance: str
    variant: str
    source_chain: Dict[str, Any] = field(default_factory=dict)
    verification_chain: List[Dict[str, Any]] = field(default_factory=list)
    confidence_score: float = 0.0
    label_quality: str = "synthetic_verified"
    generation_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return asdict(self)


# ---------------------------------------------------------------------------
# 追踪器
# ---------------------------------------------------------------------------

class ProvenanceTracker:
    """
    来源链与验证链追踪器。

    公共接口：
      - record_seed(seed) -> None
      - record_generalization(seed, variants, metadata) -> None
      - record_verification(seed, variant, verification_result) -> None
      - build_record(seed, variant, gen_metadata, ver_result) -> OrbitRecord
      - save(output_path) -> None
      - get_records() -> List[OrbitRecord]
      - get_statistics() -> Dict
    """

    def __init__(self, trace_path: Optional[str] = None):
        self._records: List[OrbitRecord] = []
        self._trace_path = trace_path
        self._trace_lines: List[Dict[str, Any]] = []

    def record_seed(self, seed: Seed) -> None:
        """
        记录种子生成事件。

        参数:
            seed: 生成的种子
        """
        event = {
            "event": "seed_generated",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "seed_id": seed.seed_id,
            "domain": seed.domain,
            "function": seed.function,
            "standard_utterance": seed.standard_utterance,
            "source_type": seed.source_type,
        }
        self._trace_lines.append(event)
        logger.debug("记录种子事件: %s", seed.seed_id)

    def record_generalization(
        self,
        seed: Seed,
        variants: List[str],
        metadata: Dict[str, Any],
    ) -> None:
        """
        记录泛化事件。

        参数:
            seed: 源种子
            variants: 生成的变体列表
            metadata: 生成元数据（模型、维度、时间戳等）
        """
        event = {
            "event": "generalization_completed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "seed_id": seed.seed_id,
            "num_variants": len(variants),
            "variants": variants,
            "metadata": metadata,
        }
        self._trace_lines.append(event)
        logger.debug("记录泛化事件: seed=%s, variants=%d", seed.seed_id, len(variants))

    def record_verification(
        self,
        seed: Seed,
        variant: str,
        verification_result: Dict[str, Any],
    ) -> None:
        """
        记录验证事件。

        参数:
            seed: 源种子
            variant: 被验证的变体
            verification_result: 验证结果
        """
        event = {
            "event": "verification_completed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "seed_id": seed.seed_id,
            "variant": variant,
            "overall_passed": verification_result.get("overall_passed", False),
            "confidence_score": verification_result.get("confidence_score", 0.0),
        }
        self._trace_lines.append(event)

    def build_record(
        self,
        seed: Seed,
        variant: str,
        gen_metadata: Dict[str, Any],
        ver_result: Dict[str, Any],
    ) -> OrbitRecord:
        """
        构建最终输出记录。

        参数:
            seed: 源种子
            variant: 变体文本
            gen_metadata: 泛化元数据
            ver_result: 验证结果

        返回:
            完整的 OrbitRecord
        """
        record_id = f"orbit_{seed.seed_id}_{uuid.uuid4().hex[:6]}"

        # 构建来源链
        source_chain = {
            "seed_id": seed.seed_id,
            "domain": seed.domain,
            "function": seed.function,
            "sub_function": seed.sub_function,
            "params": seed.params,
            "source_type": seed.source_type,
        }

        # 构建验证链
        verification_chain = []
        for stage_key in ["rule_check", "semantic_check", "safety_check"]:
            if stage_key in ver_result:
                verification_chain.append(ver_result[stage_key])

        record = OrbitRecord(
            record_id=record_id,
            standard_utterance=seed.standard_utterance,
            variant=variant,
            source_chain=source_chain,
            verification_chain=verification_chain,
            confidence_score=ver_result.get("confidence_score", 0.0),
            label_quality="synthetic_verified" if ver_result.get("overall_passed") else "synthetic_rejected",
            generation_metadata=gen_metadata,
        )

        self._records.append(record)
        return record

    def save(self, output_path: str) -> None:
        """
        将所有记录保存到 JSON 文件。

        参数:
            output_path: 输出文件路径
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        data = [r.to_dict() for r in self._records]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info("已保存 %d 条记录到 %s", len(data), output_path)

    def save_trace(self) -> None:
        """将轨迹保存到 JSONL 文件。"""
        if not self._trace_path:
            logger.debug("未设置轨迹路径，跳过保存")
            return

        path = Path(self._trace_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            for event in self._trace_lines:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")

        logger.info("已保存 %d 条轨迹到 %s", len(self._trace_lines), self._trace_path)

    def get_records(self) -> List[OrbitRecord]:
        """获取所有记录。"""
        return self._records

    def get_statistics(self) -> Dict[str, Any]:
        """
        获取统计信息。

        返回:
            包含总记录数、各层通过率、平均置信度等统计信息的字典
        """
        total = len(self._records)
        if total == 0:
            return {
                "total_records": 0,
                "total_passed": 0,
                "total_rejected": 0,
                "pass_rate": 0.0,
                "avg_confidence": 0.0,
                "by_domain": {},
            }

        passed = sum(1 for r in self._records if r.label_quality == "synthetic_verified")
        rejected = total - passed
        avg_conf = sum(r.confidence_score for r in self._records) / total

        # 按领域统计
        by_domain: Dict[str, Dict[str, Any]] = {}
        for r in self._records:
            domain = r.source_chain.get("domain", "unknown")
            if domain not in by_domain:
                by_domain[domain] = {"total": 0, "passed": 0, "scores": []}
            by_domain[domain]["total"] += 1
            if r.label_quality == "synthetic_verified":
                by_domain[domain]["passed"] += 1
            by_domain[domain]["scores"].append(r.confidence_score)

        for domain, stats in by_domain.items():
            stats["pass_rate"] = round(stats["passed"] / stats["total"], 3) if stats["total"] > 0 else 0.0
            stats["avg_confidence"] = round(sum(stats["scores"]) / len(stats["scores"]), 3) if stats["scores"] else 0.0
            del stats["scores"]

        return {
            "total_records": total,
            "total_passed": passed,
            "total_rejected": rejected,
            "pass_rate": round(passed / total, 3),
            "avg_confidence": round(avg_conf, 3),
            "by_domain": by_domain,
        }

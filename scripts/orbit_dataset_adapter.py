"""
ORBIT 数据集适配器 — 将 ORBIT 流水线输出转换为多种格式。

支持的输出格式：
  1. JSON — 完整的记录列表
  2. JSONL — 每行一条记录（便于流式处理）
  3. Excel — 带格式的表格（便于人工审核）
  4. 统计摘要 — 各层通过率、置信度分布等
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from core.provenance_tracker import OrbitRecord

logger = logging.getLogger(__name__)


class OrbitDatasetAdapter:
    """
    ORBIT 数据集适配器。

    公共接口：
      - to_json(records, output_path) -> str
      - to_jsonl(records, output_path) -> str
      - to_excel(records, output_path) -> str
      - generate_summary(records) -> Dict
    """

    def to_json(
        self, records: List[OrbitRecord], output_path: str
    ) -> str:
        """
        将记录列表导出为 JSON 文件。

        参数:
            records: OrbitRecord 列表
            output_path: 输出文件路径

        返回:
            实际写入的文件路径
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        data = [r.to_dict() for r in records]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info("已导出 %d 条记录到 JSON: %s", len(records), path)
        return str(path)

    def to_jsonl(
        self, records: List[OrbitRecord], output_path: str
    ) -> str:
        """
        将记录列表导出为 JSONL 文件（每行一条记录）。

        参数:
            records: OrbitRecord 列表
            output_path: 输出文件路径

        返回:
            实际写入的文件路径
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")

        logger.info("已导出 %d 条记录到 JSONL: %s", len(records), path)
        return str(path)

    def to_excel(
        self, records: List[OrbitRecord], output_path: str
    ) -> str:
        """
        将记录列表导出为 Excel 文件。

        参数:
            records: OrbitRecord 列表
            output_path: 输出文件路径

        返回:
            实际写入的文件路径
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        rows = []
        for r in records:
            # 提取验证链中各层分数
            rule_score = 0.0
            semantic_score = 0.0
            safety_score = 0.0
            rule_passed = False
            semantic_passed = False
            safety_passed = False

            for stage in r.verification_chain:
                if stage.get("stage") == "rule":
                    rule_score = stage.get("score", 0.0)
                    rule_passed = stage.get("passed", False)
                elif stage.get("stage") == "semantic":
                    semantic_score = stage.get("score", 0.0)
                    semantic_passed = stage.get("passed", False)
                elif stage.get("stage") == "safety":
                    safety_score = stage.get("score", 0.0)
                    safety_passed = stage.get("passed", False)

            rows.append({
                "record_id": r.record_id,
                "领域": r.source_chain.get("domain", ""),
                "功能": r.source_chain.get("function", ""),
                "标准话术": r.standard_utterance,
                "泛化变体": r.variant,
                "规则验证": "通过" if rule_passed else "未通过",
                "规则分数": rule_score,
                "语义分数": semantic_score,
                "语义验证": "通过" if semantic_passed else "未通过",
                "安全分数": safety_score,
                "安全验证": "通过" if safety_passed else "未通过",
                "综合置信度": r.confidence_score,
                "质量标签": r.label_quality,
            })

        df = pd.DataFrame(rows)
        df.to_excel(path, index=False, engine="openpyxl")

        logger.info("已导出 %d 条记录到 Excel: %s", len(records), path)
        return str(path)

    def generate_summary(
        self, records: List[OrbitRecord]
    ) -> Dict[str, Any]:
        """
        生成统计摘要。

        返回:
            包含总记录数、通过率、平均置信度等统计信息
        """
        total = len(records)
        if total == 0:
            return {
                "total_records": 0,
                "total_passed": 0,
                "total_rejected": 0,
                "pass_rate": 0.0,
                "avg_confidence": 0.0,
                "by_domain": {},
                "by_stage": {
                    "rule": {"total": 0, "passed": 0, "pass_rate": 0.0},
                    "semantic": {"total": 0, "passed": 0, "pass_rate": 0.0},
                    "safety": {"total": 0, "passed": 0, "pass_rate": 0.0},
                },
            }

        passed = sum(1 for r in records if r.label_quality == "synthetic_verified")
        rejected = total - passed
        avg_conf = sum(r.confidence_score for r in records) / total

        # 按领域统计
        by_domain: Dict[str, Dict[str, Any]] = {}
        for r in records:
            domain = r.source_chain.get("domain", "unknown")
            if domain not in by_domain:
                by_domain[domain] = {"total": 0, "passed": 0}
            by_domain[domain]["total"] += 1
            if r.label_quality == "synthetic_verified":
                by_domain[domain]["passed"] += 1

        for stats in by_domain.values():
            stats["pass_rate"] = round(stats["passed"] / stats["total"], 3) if stats["total"] > 0 else 0.0

        # 按验证阶段统计
        by_stage: Dict[str, Dict[str, int]] = {
            "rule": {"total": 0, "passed": 0},
            "semantic": {"total": 0, "passed": 0},
            "safety": {"total": 0, "passed": 0},
        }
        for r in records:
            for stage_data in r.verification_chain:
                stage_name = stage_data.get("stage", "")
                if stage_name in by_stage:
                    if stage_data.get("reason") != "skipped":
                        by_stage[stage_name]["total"] += 1
                        if stage_data.get("passed"):
                            by_stage[stage_name]["passed"] += 1

        for stats in by_stage.values():
            stats["pass_rate"] = round(stats["passed"] / stats["total"], 3) if stats["total"] > 0 else 0.0

        return {
            "total_records": total,
            "total_passed": passed,
            "total_rejected": rejected,
            "pass_rate": round(passed / total, 3),
            "avg_confidence": round(avg_conf, 3),
            "by_domain": by_domain,
            "by_stage": by_stage,
        }

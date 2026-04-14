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
        raise NotImplementedError("将在第4阶段实现")

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
        raise NotImplementedError("将在第4阶段实现")

    def to_excel(
        self, records: List[OrbitRecord], output_path: str
    ) -> str:
        """
        将记录列表导出为 Excel 文件。

        列包括：record_id, standard_utterance, variant,
        domain, function, confidence_score, rule_passed,
        semantic_score, safety_score, label_quality

        参数:
            records: OrbitRecord 列表
            output_path: 输出文件路径

        返回:
            实际写入的文件路径
        """
        raise NotImplementedError("将在第4阶段实现")

    def generate_summary(
        self, records: List[OrbitRecord]
    ) -> Dict[str, Any]:
        """
        生成统计摘要。

        返回:
            {
                "total_records": int,
                "total_passed": int,
                "pass_rate": float,
                "avg_confidence": float,
                "by_domain": {...},
                "by_stage": {...},
            }
        """
        raise NotImplementedError("将在第4阶段实现")

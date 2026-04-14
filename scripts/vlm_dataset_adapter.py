"""
VLM 数据集适配器 — 训练导出与审阅导出的双轨结构。

训练导出：生成 JSONL 格式的训练数据（messages + images）
审阅导出：生成 Excel 格式的审阅报告（含提示词、失败原因、模型版本等）

公共接口：
  - export_training(records, output_path) -> ExportSummary
  - export_review(records, output_path) -> ExportSummary
  - export_all(records, output_dir) -> Dict[str, ExportSummary]
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.contracts import VLMRecord, LabelQuality

logger = logging.getLogger(__name__)


@dataclass
class ExportSummary:
    """导出摘要。"""

    format: str = ""
    output_path: str = ""
    total_records: int = 0
    verified_count: int = 0
    rejected_count: int = 0
    errors: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return {
            "format": self.format,
            "output_path": self.output_path,
            "total_records": self.total_records,
            "verified_count": self.verified_count,
            "rejected_count": self.rejected_count,
            "errors": self.errors,
        }


class VLMDatasetAdapter:
    """
    VLM 数据集适配器。

    公共接口：
      - export_training(records, output_path) -> ExportSummary
      - export_review(records, output_path) -> ExportSummary
      - export_all(records, output_dir) -> Dict[str, ExportSummary]

    目录结构契约：
      output/vlm/
        ├── training/
        │   └── vlm_train_{run_id}.jsonl
        ├── review/
        │   └── vlm_review_{run_id}.xlsx
        └── images/
            └── vlm_img_*.png
    """

    def export_training(
        self,
        records: List[VLMRecord],
        output_path: str,
    ) -> ExportSummary:
        """
        导出训练数据（JSONL 格式）。

        每行一个 JSON 对象，包含 messages 和 images 字段，
        兼容 OpenAI fine-tuning 格式。

        仅导出 label_quality == "synthetic_verified" 的记录。

        参数:
            records: VLMRecord 列表
            output_path: 输出文件路径（.jsonl）

        返回:
            ExportSummary 导出摘要
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        verified = [
            r for r in records
            if r.label_quality == LabelQuality.VERIFIED.value
        ]
        rejected = [
            r for r in records
            if r.label_quality != LabelQuality.VERIFIED.value
        ]

        errors: List[str] = []
        written = 0

        with open(path, "w", encoding="utf-8") as f:
            for record in verified:
                try:
                    line = json.dumps(
                        {
                            "messages": record.messages,
                            "images": record.images,
                            "record_id": record.record_id,
                            "confidence_score": record.confidence_score,
                        },
                        ensure_ascii=False,
                    )
                    f.write(line + "\n")
                    written += 1
                except Exception as e:
                    errors.append(
                        f"记录 {record.record_id} 导出失败: {e}"
                    )

        logger.info(
            "训练数据导出完成: %d 条记录写入 %s",
            written, output_path,
        )

        return ExportSummary(
            format="jsonl",
            output_path=str(path),
            total_records=len(records),
            verified_count=written,
            rejected_count=len(rejected),
            errors=errors,
        )

    def export_review(
        self,
        records: List[VLMRecord],
        output_path: str,
    ) -> ExportSummary:
        """
        导出审阅报告（Excel 格式）。

        包含所有记录（含被拒绝的），附带审阅专用字段。

        参数:
            records: VLMRecord 列表
            output_path: 输出文件路径（.xlsx）

        返回:
            ExportSummary 导出摘要
        """
        import openpyxl

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "VLM 审阅报告"

        # 表头
        headers = [
            "record_id", "run_id", "label_quality", "confidence_score",
            "question", "answer", "image_prompt", "statement",
            "image_path", "generation_model", "image_generation_model",
            "failure_reason", "verification_summary",
            "task_category", "seed_id",
        ]
        ws.append(headers)

        errors: List[str] = []
        verified_count = 0
        rejected_count = 0

        for record in records:
            try:
                # 提取 messages 中的 question 和 answer
                question = ""
                answer = ""
                for msg in record.messages:
                    if msg.get("role") == "user":
                        question = msg.get("content", "")
                    elif msg.get("role") == "assistant":
                        answer = msg.get("content", "")

                review = record.review_fields or {}
                source = record.source_chain or {}

                # 验证摘要
                verification_summary = "; ".join(
                    f"{v.get('stage', '?')}: {v.get('score', 0):.2f}"
                    for v in record.verification_chain
                    if isinstance(v, dict)
                )

                row = [
                    record.record_id,
                    record.run_id,
                    record.label_quality,
                    record.confidence_score,
                    question,
                    answer,
                    review.get("image_prompt", ""),
                    review.get("statement", ""),
                    record.images[0] if record.images else "",
                    review.get("generation_model", ""),
                    review.get("image_generation_model", ""),
                    review.get("failure_reason", ""),
                    verification_summary,
                    source.get("task_category", ""),
                    source.get("seed_id", ""),
                ]
                ws.append(row)

                if record.label_quality == LabelQuality.VERIFIED.value:
                    verified_count += 1
                else:
                    rejected_count += 1

            except Exception as e:
                errors.append(f"记录 {record.record_id} 导出失败: {e}")

        wb.save(str(path))
        logger.info(
            "审阅报告导出完成: %d 条记录写入 %s",
            len(records), output_path,
        )

        return ExportSummary(
            format="xlsx",
            output_path=str(path),
            total_records=len(records),
            verified_count=verified_count,
            rejected_count=rejected_count,
            errors=errors,
        )

    def export_all(
        self,
        records: List[VLMRecord],
        output_dir: str,
        run_id: str = "default",
    ) -> Dict[str, ExportSummary]:
        """
        同时导出训练数据和审阅报告。

        参数:
            records: VLMRecord 列表
            output_dir: 输出目录
            run_id: 运行批次标识

        返回:
            {"training": ExportSummary, "review": ExportSummary}
        """
        training_path = f"{output_dir}/training/vlm_train_{run_id}.jsonl"
        review_path = f"{output_dir}/review/vlm_review_{run_id}.xlsx"

        training_summary = self.export_training(records, training_path)
        review_summary = self.export_review(records, review_path)

        return {
            "training": training_summary,
            "review": review_summary,
        }

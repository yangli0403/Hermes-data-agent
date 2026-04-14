"""
结构校验器 — 对 VLMSample 执行纯结构校验。

零 API 成本的第一层验证，用于快速过滤明显不合格的样本。
校验内容包括字段完整性、类型约束、路径存在性和基础格式合法性。

公共接口：
  - verify(sample) -> StageResult
  - verify_batch(samples) -> List[StageResult]
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import List

from core.contracts import VLMSample
from core.rule_verifier import StageResult

logger = logging.getLogger(__name__)


class SchemaVerifier:
    """
    结构校验器。

    公共接口：
      - verify(sample) -> StageResult
      - verify_batch(samples) -> List[StageResult]
    """

    # 必填文本字段及其最小长度
    REQUIRED_TEXT_FIELDS = {
        "question": 2,
        "answer": 1,
        "image_prompt": 5,
        "statement": 2,
    }

    # 问题文本最大长度
    MAX_QUESTION_LENGTH = 500
    MAX_ANSWER_LENGTH = 2000
    MAX_PROMPT_LENGTH = 2000

    def verify(self, sample: VLMSample) -> StageResult:
        """
        对单个 VLMSample 执行结构校验。

        校验规则：
          1. 必填文本字段不为空且满足最小长度
          2. 文本字段不超过最大长度
          3. 如果已生成图像，图像路径必须存在
          4. seed_id 不为空
          5. 样本状态不为 "failed"

        参数:
            sample: 待校验的候选样本

        返回:
            StageResult 校验结果
        """
        errors: List[str] = []

        # 1. 检查样本状态
        if sample.status == "failed":
            return StageResult(
                stage="schema",
                passed=False,
                score=0.0,
                reason=f"样本已标记为失败: {sample.failure_reason or '未知原因'}",
            )

        # 2. 检查 seed_id
        if not sample.seed_id:
            errors.append("seed_id 为空")

        # 3. 检查必填文本字段
        field_values = {
            "question": sample.question,
            "answer": sample.answer,
            "image_prompt": sample.image_prompt,
            "statement": sample.statement,
        }

        for field_name, min_len in self.REQUIRED_TEXT_FIELDS.items():
            value = field_values.get(field_name, "")
            if not value or not value.strip():
                errors.append(f"{field_name} 为空")
            elif len(value.strip()) < min_len:
                errors.append(
                    f"{field_name} 长度不足（最小 {min_len} 字符，实际 {len(value.strip())}）"
                )

        # 4. 检查 question 以问号结尾
        if sample.question and sample.question.strip():
            q = sample.question.strip()
            if not q.endswith("?") and not q.endswith("？"):
                errors.append("question 应以问号结尾（? 或 ？）")

        # 5. 检查 image_prompt 为英文（不包含中文字符）
        if sample.image_prompt and sample.image_prompt.strip():
            if re.search(r'[\u4e00-\u9fff]', sample.image_prompt):
                errors.append("image_prompt 应为英文，不应包含中文字符")

        # 6. 检查文本长度上限
        if sample.question and len(sample.question) > self.MAX_QUESTION_LENGTH:
            errors.append(
                f"question 超过最大长度 {self.MAX_QUESTION_LENGTH}（实际 {len(sample.question)}）"
            )
        if sample.answer and len(sample.answer) > self.MAX_ANSWER_LENGTH:
            errors.append(
                f"answer 超过最大长度 {self.MAX_ANSWER_LENGTH}（实际 {len(sample.answer)}）"
            )
        if sample.image_prompt and len(sample.image_prompt) > self.MAX_PROMPT_LENGTH:
            errors.append(
                f"image_prompt 超过最大长度 {self.MAX_PROMPT_LENGTH}（实际 {len(sample.image_prompt)}）"
            )

        # 5. 检查图像路径（如果已生成）
        if sample.image_path:
            if not Path(sample.image_path).exists():
                errors.append(f"图像文件不存在: {sample.image_path}")

        # 汇总结果
        if errors:
            return StageResult(
                stage="schema",
                passed=False,
                score=0.0,
                reason="结构校验失败: " + "; ".join(errors),
            )

        return StageResult(
            stage="schema",
            passed=True,
            score=1.0,
            reason="结构校验通过",
        )

    def verify_batch(self, samples: List[VLMSample]) -> List[StageResult]:
        """
        批量结构校验。

        参数:
            samples: 样本列表

        返回:
            StageResult 列表
        """
        return [self.verify(sample) for sample in samples]

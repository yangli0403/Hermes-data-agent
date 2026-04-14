"""
VLM 覆盖率补充测试 — 针对覆盖率报告中未覆盖的边界条件和代码路径。

目标模块：
  - core/client_factory.py (70% → 100%)
  - core/contracts.py (93% → 98%+)
  - core/schema_verifier.py (83% → 95%+)
  - core/vlm_client.py (79% → 85%+)
  - core/vision_consistency_verifier.py (79% → 90%+)
  - core/image_synthesis_coordinator.py (93% → 98%+)
"""

import json
import os
import tempfile
from dataclasses import asdict
from unittest.mock import MagicMock, patch

import pytest

# ---- 导入被测模块 ----
from core.client_factory import ClientFactory
from core.contracts import (
    BaseRecord,
    LabelQuality,
    QuestionType,
    VisualSeed,
    VLMSample,
    VLMRecord,
)
from core.schema_verifier import SchemaVerifier
from core.vlm_client import VLMJudgment
from core.vision_consistency_verifier import VisionConsistencyVerifier
from core.image_synthesis_coordinator import ImageSynthesisCoordinator


# =====================================================================
# 辅助函数
# =====================================================================

def _make_vlm_sample(**overrides) -> VLMSample:
    """创建默认的 VLMSample 用于测试。"""
    defaults = dict(
        seed_id="vseed_test001",
        question="这张图片中有什么动物？",
        answer="一只猫",
        image_prompt="A cute cat sitting on a windowsill in warm sunlight",
        statement="图片中有一只猫坐在窗台上",
    )
    defaults.update(overrides)
    return VLMSample(**defaults)


# =====================================================================
# ClientFactory 覆盖率补充
# =====================================================================

class TestClientFactoryCoverage:
    """补充 ClientFactory 的实际创建路径测试。"""

    def test_create_llm_client_with_config(self):
        """测试使用自定义配置创建 LLM 客户端。"""
        config = {"model": "gpt-4.1-nano", "max_retries": 5, "retry_delay": 2.0}
        client = ClientFactory.create_llm_client(config)
        assert client._model == "gpt-4.1-nano"
        assert client._max_retries == 5

    def test_create_llm_client_default(self):
        """测试使用默认配置创建 LLM 客户端。"""
        client = ClientFactory.create_llm_client()
        assert client._model == "gpt-4.1-mini"

    def test_create_image_client_with_config(self):
        """测试使用自定义配置创建图像客户端。"""
        config = {"model": "dall-e-2", "max_retries": 2, "retry_delay": 1.0, "timeout": 60.0}
        client = ClientFactory.create_image_client(config)
        assert client._model == "dall-e-2"

    def test_create_image_client_default(self):
        """测试使用默认配置创建图像客户端。"""
        client = ClientFactory.create_image_client()
        assert client._model == "dall-e-3"

    def test_create_vlm_client_with_config(self):
        """测试使用自定义配置创建 VLM 客户端。"""
        config = {"model": "gpt-4.1-mini", "max_retries": 2, "retry_delay": 0.5, "max_tokens": 500}
        client = ClientFactory.create_vlm_client(config)
        assert client._model == "gpt-4.1-mini"
        assert client._max_tokens == 500

    def test_create_vlm_client_default(self):
        """测试使用默认配置创建 VLM 客户端。"""
        client = ClientFactory.create_vlm_client()
        assert client._model == "gpt-4.1-mini"


# =====================================================================
# Contracts 覆盖率补充
# =====================================================================

class TestContractsCoverage:
    """补充 contracts.py 的未覆盖路径。"""

    def test_base_record_auto_fields(self):
        """测试 BaseRecord 自动生成 record_id 和 created_at。"""
        record = BaseRecord()
        assert record.record_id.startswith("rec_")
        assert record.created_at != ""

    def test_base_record_to_dict(self):
        """测试 BaseRecord.to_dict()。"""
        record = BaseRecord(run_id="run_001")
        d = record.to_dict()
        assert d["run_id"] == "run_001"
        assert "record_id" in d

    def test_visual_seed_from_dict(self):
        """测试 VisualSeed.from_dict() 工厂方法。"""
        data = {
            "seed_id": "vseed_abc",
            "task_category": "object_recognition",
            "scene_description": "室内场景",
            "entities": ["猫", "窗台"],
            "question_type": "descriptive",
            "answer_style": "detailed",
            "constraints": {"min_entities": 1},
            "image_style": "cartoon",
            "source_config": "test.yaml",
            "metadata": {"key": "value"},
        }
        seed = VisualSeed.from_dict(data)
        assert seed.seed_id == "vseed_abc"
        assert seed.task_category == "object_recognition"
        assert seed.image_style == "cartoon"

    def test_vlm_sample_from_dict(self):
        """测试 VLMSample.from_dict() 工厂方法。"""
        data = {
            "sample_id": "vsample_xyz",
            "seed_id": "vseed_001",
            "question": "这是什么？",
            "answer": "一只猫",
            "image_prompt": "A cat on a table",
            "statement": "桌上有猫",
            "image_path": "/tmp/test.png",
            "status": "verified",
        }
        sample = VLMSample.from_dict(data)
        assert sample.sample_id == "vsample_xyz"
        assert sample.status == "verified"
        assert sample.image_path == "/tmp/test.png"

    def test_vlm_record_from_dict(self):
        """测试 VLMRecord.from_dict() 工厂方法。"""
        data = {
            "record_id": "vlm_abc123",
            "run_id": "run_001",
            "messages": [{"role": "user", "content": "test"}],
            "images": ["/tmp/img.png"],
            "confidence_score": 0.95,
            "label_quality": "verified",
        }
        record = VLMRecord.from_dict(data)
        assert record.record_id == "vlm_abc123"
        assert record.confidence_score == 0.95

    def test_question_type_enum_values(self):
        """测试 QuestionType 枚举的所有值。"""
        assert QuestionType.DESCRIPTIVE.value == "descriptive"
        assert QuestionType.COUNTING.value == "counting"
        assert QuestionType.SPATIAL.value == "spatial"
        assert QuestionType.COMPARATIVE.value == "comparative"
        assert QuestionType.REASONING.value == "reasoning"


# =====================================================================
# SchemaVerifier 覆盖率补充
# =====================================================================

class TestSchemaVerifierCoverage:
    """补充 SchemaVerifier 的边界条件测试。"""

    def test_failed_status_sample(self):
        """测试已标记为失败的样本直接返回失败。"""
        verifier = SchemaVerifier()
        sample = _make_vlm_sample(status="failed", failure_reason="图像生成超时")
        result = verifier.verify(sample)
        assert result.passed is False
        assert "图像生成超时" in result.reason

    def test_empty_seed_id(self):
        """测试 seed_id 为空时报错。"""
        verifier = SchemaVerifier()
        sample = _make_vlm_sample(seed_id="")
        result = verifier.verify(sample)
        assert result.passed is False
        assert "seed_id" in result.reason

    def test_field_too_short(self):
        """测试文本字段长度不足。"""
        verifier = SchemaVerifier()
        sample = _make_vlm_sample(image_prompt="A")  # 最小 5 字符
        result = verifier.verify(sample)
        assert result.passed is False
        assert "长度不足" in result.reason

    def test_question_too_long(self):
        """测试 question 超过最大长度。"""
        verifier = SchemaVerifier()
        sample = _make_vlm_sample(question="这是什么？" * 200)
        result = verifier.verify(sample)
        assert result.passed is False
        assert "超过最大长度" in result.reason

    def test_answer_too_long(self):
        """测试 answer 超过最大长度。"""
        verifier = SchemaVerifier()
        sample = _make_vlm_sample(answer="x" * 2500)
        result = verifier.verify(sample)
        assert result.passed is False
        assert "超过最大长度" in result.reason

    def test_image_prompt_too_long(self):
        """测试 image_prompt 超过最大长度。"""
        verifier = SchemaVerifier()
        sample = _make_vlm_sample(image_prompt="A cat " * 500)
        result = verifier.verify(sample)
        assert result.passed is False
        assert "超过最大长度" in result.reason

    def test_image_path_not_exists(self):
        """测试图像路径不存在时报错。"""
        verifier = SchemaVerifier()
        sample = _make_vlm_sample(image_path="/nonexistent/path/image.png")
        result = verifier.verify(sample)
        assert result.passed is False
        assert "图像文件不存在" in result.reason


# =====================================================================
# VisionConsistencyVerifier 覆盖率补充
# =====================================================================

class TestVisionConsistencyVerifierCoverage:
    """补充 VisionConsistencyVerifier 的边界条件测试。"""

    def test_verify_file_not_found_exception(self):
        """测试 VLM judge 抛出 FileNotFoundError 时的处理。"""
        mock_vlm = MagicMock()
        mock_vlm.judge.side_effect = FileNotFoundError("图像已被删除")

        verifier = VisionConsistencyVerifier(vlm_client=mock_vlm)

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"fake")
            img_path = f.name

        try:
            sample = _make_vlm_sample()
            sample.image_path = img_path
            result = verifier.verify(sample)

            assert result.passed is False
            assert "图像文件不存在" in result.reason
        finally:
            os.unlink(img_path)

    def test_verify_batch(self):
        """测试批量验证。"""
        mock_vlm = MagicMock()
        mock_vlm.judge.return_value = VLMJudgment(
            passed=True, score=0.9, reason="OK", model="gpt-4.1-mini"
        )
        mock_vlm.judge_consistency.return_value = VLMJudgment(
            passed=True, score=0.85, reason="OK", model="gpt-4.1-mini"
        )

        verifier = VisionConsistencyVerifier(vlm_client=mock_vlm)

        samples = []
        tmp_files = []
        for _ in range(3):
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                f.write(b"fake")
                tmp_files.append(f.name)
            s = _make_vlm_sample()
            s.image_path = tmp_files[-1]
            samples.append(s)

        try:
            results = verifier.verify_batch(samples)
            assert len(results) == 3
            assert all(r.passed for r in results)
        finally:
            for p in tmp_files:
                os.unlink(p)


# =====================================================================
# ImageSynthesisCoordinator 覆盖率补充
# =====================================================================

class TestImageSynthesisCoordinatorCoverage:
    """补充 ImageSynthesisCoordinator 的边界条件测试。"""

    def test_synthesize_batch_skip_failed(self):
        """测试批量合成时跳过已失败样本。"""
        mock_image_client = MagicMock()
        coordinator = ImageSynthesisCoordinator(image_client=mock_image_client)

        failed_sample = _make_vlm_sample(status="failed")
        normal_sample = _make_vlm_sample()

        # mock synthesize 对 normal_sample 的调用
        from core.image_client import ImageResult
        mock_image_client.generate.return_value = ImageResult(
            success=True,
            image_path="/tmp/out.png",
            model="dall-e-3",
            prompt="A cat",
            resolution="1024x1024",
        )

        results = coordinator.synthesize_batch(
            [failed_sample, normal_sample],
            output_dir="/tmp"
        )
        assert len(results) == 2
        # 失败样本应被跳过
        assert results[0].status == "failed"

    def test_synthesize_batch_skip_has_image(self):
        """测试批量合成时跳过已有图像的样本。"""
        mock_image_client = MagicMock()
        coordinator = ImageSynthesisCoordinator(image_client=mock_image_client)

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"fake")
            img_path = f.name

        try:
            sample_with_image = _make_vlm_sample()
            sample_with_image.image_path = img_path
            sample_with_image.status = "image_generated"

            results = coordinator.synthesize_batch(
                [sample_with_image],
                output_dir="/tmp"
            )
            assert len(results) == 1
            # 不应调用 generate
            mock_image_client.generate.assert_not_called()
        finally:
            os.unlink(img_path)


# =====================================================================
# VLMClient 覆盖率补充（_extract_json 边界路径）
# =====================================================================

class TestVLMClientExtractJson:
    """补充 VLMClient._extract_json 的多种 JSON 提取路径。"""

    def test_extract_json_from_code_block(self):
        """测试从 ```json ... ``` 代码块中提取 JSON。"""
        from core.vlm_client import VLMClient
        client = VLMClient()

        text = '```json\n{"score": 0.8, "reason": "good"}\n```'
        result = client._extract_json(text)
        assert result["score"] == 0.8

    def test_extract_json_from_curly_braces(self):
        """测试从文本中提取第一个 { ... } 块。"""
        from core.vlm_client import VLMClient
        client = VLMClient()

        text = 'Here is the result: {"score": 0.7, "reason": "ok"} and more text'
        result = client._extract_json(text)
        assert result["score"] == 0.7

    def test_extract_json_failure(self):
        """测试无法提取 JSON 时抛出异常。"""
        from core.vlm_client import VLMClient
        client = VLMClient()

        with pytest.raises(json.JSONDecodeError):
            client._extract_json("no json here at all")

    def test_extract_json_invalid_code_block(self):
        """测试代码块中的无效 JSON 回退到 {} 提取。"""
        from core.vlm_client import VLMClient
        client = VLMClient()

        text = '```json\nnot valid json\n```\n{"score": 0.5}'
        result = client._extract_json(text)
        assert result["score"] == 0.5

    def test_extract_json_invalid_all(self):
        """测试所有提取方式都失败时抛出异常。"""
        from core.vlm_client import VLMClient
        client = VLMClient()

        text = '```json\nnot valid\n```\n{also not valid}'
        with pytest.raises(json.JSONDecodeError):
            client._extract_json(text)


# =====================================================================
# VLMClient describe 方法测试
# =====================================================================

class TestVLMClientDescribe:
    """测试 VLMClient.describe 方法的不同 detail_level。"""

    def test_describe_brief(self):
        """测试 brief 详细程度。"""
        from core.vlm_client import VLMClient
        client = VLMClient()
        client._client = MagicMock()

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "一只猫坐在窗台上"
        client._client.chat.completions.create.return_value = mock_response

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"fake image data")
            img_path = f.name

        try:
            result = client.describe(img_path, detail_level="brief")
            assert "猫" in result
        finally:
            os.unlink(img_path)

    def test_describe_detailed(self):
        """测试 detailed 详细程度。"""
        from core.vlm_client import VLMClient
        client = VLMClient()
        client._client = MagicMock()

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "详细描述内容"
        client._client.chat.completions.create.return_value = mock_response

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"fake image data")
            img_path = f.name

        try:
            result = client.describe(img_path, detail_level="detailed")
            assert len(result) > 0
        finally:
            os.unlink(img_path)

    def test_validate_image_path_not_file(self):
        """测试路径存在但不是文件时的校验。"""
        from core.vlm_client import VLMClient
        client = VLMClient()

        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValueError, match="路径不是文件"):
                client._validate_image_path(tmpdir)

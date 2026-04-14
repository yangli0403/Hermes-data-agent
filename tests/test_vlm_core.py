"""
VLM 视觉链路核心模块单元测试。

覆盖：contracts (VisualSeed, VLMSample, VLMRecord)、ConfigLoader (vlm)、
       VisualSeedEngine、SchemaVerifier、VLMDatasetAdapter
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.contracts import (
    BaseRecord,
    VisualSeed,
    VLMSample,
    VLMRecord,
    LabelQuality,
    QuestionType,
)
from core.config_loader import ConfigLoader
from core.visual_seed_engine import VisualSeedEngine
from core.schema_verifier import SchemaVerifier
from scripts.vlm_dataset_adapter import VLMDatasetAdapter, ExportSummary


# =====================================================================
# 辅助函数
# =====================================================================

def _make_visual_seed(**overrides) -> VisualSeed:
    """创建测试用 VisualSeed。"""
    defaults = dict(
        task_category="scene_understanding",
        scene_description="城市十字路口，有行人和汽车",
        entities=["行人", "汽车", "红绿灯"],
        question_type="descriptive",
        answer_style="brief",
        image_style="photorealistic",
        constraints={"min_entities": 2, "language": "zh"},
    )
    defaults.update(overrides)
    return VisualSeed(**defaults)


def _make_vlm_sample(seed_id: str = "vseed_test", **overrides) -> VLMSample:
    """创建测试用 VLMSample。"""
    defaults = dict(
        seed_id=seed_id,
        question="图中有几辆汽车？",
        answer="图中有两辆汽车。",
        image_prompt="A city intersection with two cars and pedestrians",
        statement="图中包含两辆汽车和行人",
    )
    defaults.update(overrides)
    return VLMSample(**defaults)


def _make_vlm_record(
    label_quality: str = "synthetic_verified",
    confidence: float = 0.85,
) -> VLMRecord:
    """创建测试用 VLMRecord。"""
    seed = _make_visual_seed()
    sample = _make_vlm_sample(seed_id=seed.seed_id)
    sample.status = "verified"
    sample.image_path = "/tmp/test_img.png"
    sample.verification_results = [
        {"stage": "schema", "passed": True, "score": 1.0, "reason": "OK"},
        {"stage": "consistency", "passed": True, "score": 0.9, "reason": "OK"},
    ]
    record = VLMRecord.from_sample(
        sample=sample,
        seed=seed,
        run_id="test_run",
        confidence_score=confidence,
    )
    if label_quality != "synthetic_verified":
        record.label_quality = label_quality
    return record


# =====================================================================
# Contracts 测试
# =====================================================================

class TestVisualSeed:
    """VisualSeed 数据契约测试。"""

    def test_auto_id_generation(self):
        """测试 seed_id 自动生成。"""
        seed = _make_visual_seed()
        assert seed.seed_id.startswith("vseed_")
        assert len(seed.seed_id) > 6

    def test_unique_ids(self):
        """测试每次创建的 seed_id 唯一。"""
        seed1 = _make_visual_seed()
        seed2 = _make_visual_seed()
        assert seed1.seed_id != seed2.seed_id

    def test_to_dict(self):
        """测试序列化为字典。"""
        seed = _make_visual_seed()
        d = seed.to_dict()
        assert d["task_category"] == "scene_understanding"
        assert d["entities"] == ["行人", "汽车", "红绿灯"]
        assert d["question_type"] == "descriptive"
        assert "seed_id" in d

    def test_default_values(self):
        """测试默认值。"""
        seed = VisualSeed(
            task_category="test",
            scene_description="test scene",
            entities=["obj"],
            question_type="counting",
        )
        assert seed.answer_style == "brief"
        assert seed.image_style == "photorealistic"
        assert seed.constraints == {}
        assert seed.metadata == {}


class TestVLMSample:
    """VLMSample 数据契约测试。"""

    def test_auto_id_generation(self):
        """测试 sample_id 自动生成。"""
        sample = _make_vlm_sample()
        assert sample.sample_id.startswith("vsample_")

    def test_default_status(self):
        """测试默认状态为 pending。"""
        sample = _make_vlm_sample()
        assert sample.status == "pending"

    def test_is_verified_property(self):
        """测试 is_verified 属性。"""
        sample = _make_vlm_sample()
        assert not sample.is_verified
        sample.status = "verified"
        assert sample.is_verified

    def test_has_image_property(self):
        """测试 has_image 属性。"""
        sample = _make_vlm_sample()
        assert not sample.has_image
        sample.image_path = "/tmp/test.png"
        assert sample.has_image

    def test_to_dict(self):
        """测试序列化为字典。"""
        sample = _make_vlm_sample()
        d = sample.to_dict()
        assert d["question"] == "图中有几辆汽车？"
        assert d["answer"] == "图中有两辆汽车。"
        assert d["status"] == "pending"

    def test_verification_results_default_empty(self):
        """测试 verification_results 默认为空列表。"""
        sample = _make_vlm_sample()
        assert sample.verification_results == []

    def test_status_transitions(self):
        """测试状态流转。"""
        sample = _make_vlm_sample()
        assert sample.status == "pending"
        sample.status = "image_generated"
        assert sample.status == "image_generated"
        sample.status = "verified"
        assert sample.is_verified


class TestVLMRecord:
    """VLMRecord 数据契约测试。"""

    def test_from_sample(self):
        """测试从 VLMSample 构建 VLMRecord。"""
        seed = _make_visual_seed()
        sample = _make_vlm_sample(seed_id=seed.seed_id)
        sample.status = "verified"
        sample.image_path = "/tmp/test.png"

        record = VLMRecord.from_sample(sample, seed, run_id="run_1")
        assert record.record_id.startswith("vlm_")
        assert record.run_id == "run_1"
        assert record.label_quality == LabelQuality.VERIFIED.value
        assert len(record.messages) == 2
        assert record.messages[0]["role"] == "user"
        assert record.messages[1]["role"] == "assistant"

    def test_messages_format(self):
        """测试 messages 格式兼容 OpenAI。"""
        record = _make_vlm_record()
        for msg in record.messages:
            assert "role" in msg
            assert "content" in msg
            assert msg["role"] in ("user", "assistant", "system")

    def test_images_field(self):
        """测试 images 字段包含图像路径。"""
        record = _make_vlm_record()
        assert len(record.images) == 1
        assert record.images[0] == "/tmp/test_img.png"

    def test_source_chain(self):
        """测试 source_chain 包含种子信息。"""
        record = _make_vlm_record()
        sc = record.source_chain
        assert sc["task_category"] == "scene_understanding"
        assert "seed_id" in sc

    def test_verification_chain(self):
        """测试 verification_chain 包含验证结果。"""
        record = _make_vlm_record()
        assert len(record.verification_chain) == 2
        assert record.verification_chain[0]["stage"] == "schema"

    def test_to_dict(self):
        """测试序列化为字典。"""
        record = _make_vlm_record()
        d = record.to_dict()
        assert "record_id" in d
        assert "messages" in d
        assert "images" in d
        assert "label_quality" in d

    def test_review_fields(self):
        """测试审阅字段包含关键信息。"""
        record = _make_vlm_record()
        rf = record.review_fields
        assert "image_prompt" in rf
        assert "statement" in rf


class TestLabelQuality:
    """LabelQuality 枚举测试。"""

    def test_values(self):
        """测试枚举值。"""
        assert LabelQuality.VERIFIED.value == "synthetic_verified"
        assert LabelQuality.REJECTED.value == "synthetic_rejected"
        assert LabelQuality.PENDING.value == "pending_verification"


class TestQuestionType:
    """QuestionType 枚举测试。"""

    def test_values(self):
        """测试枚举值。"""
        assert QuestionType.DESCRIPTIVE.value == "descriptive"
        assert QuestionType.COUNTING.value == "counting"
        assert QuestionType.SPATIAL.value == "spatial"


# =====================================================================
# ConfigLoader VLM 配置测试
# =====================================================================

class TestConfigLoaderVLM:
    """ConfigLoader VLM 配置命名空间测试。"""

    def test_vlm_default_config(self):
        """测试 VLM 默认配置存在。"""
        loader = ConfigLoader()
        loader.load()
        vlm = loader.get_vlm_config()
        assert "model" in vlm
        assert "image" in vlm
        assert "verification" in vlm

    def test_vlm_model_defaults(self):
        """测试 VLM 模型默认值。"""
        loader = ConfigLoader()
        loader.load()
        assert loader.get("vlm.model.generation") == "gpt-4.1-mini"
        assert loader.get("vlm.model.image_generation") == "dall-e-3"

    def test_vlm_verification_defaults(self):
        """测试 VLM 验证默认值。"""
        loader = ConfigLoader()
        loader.load()
        assert loader.get("vlm.verification.consistency_threshold") == 0.7
        assert loader.get("vlm.verification.qa_weight") == 0.6

    def test_vlm_config_override(self):
        """测试 VLM 配置覆盖。"""
        loader = ConfigLoader()
        loader.load()
        loader.override("vlm.model.image_generation", "stable-diffusion-xl")
        assert loader.get("vlm.model.image_generation") == "stable-diffusion-xl"

    def test_vlm_yaml_merge(self):
        """测试 VLM YAML 配置合并。"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({"vlm": {"model": {"image_generation": "sd-xl"}}}, f)
            f.flush()
            loader = ConfigLoader(config_path=f.name)
            assert loader.get("vlm.model.image_generation") == "sd-xl"
            # 其他默认值应保留
            assert loader.get("vlm.model.generation") == "gpt-4.1-mini"
        os.unlink(f.name)


# =====================================================================
# VisualSeedEngine 测试
# =====================================================================

class TestVisualSeedEngine:
    """VisualSeedEngine 单元测试。"""

    def _write_vlm_config(self) -> str:
        """写入测试用 VLM 配置文件，返回路径。"""
        config = {
            "vlm_tasks": [
                {
                    "category": "scene_understanding",
                    "scenes": [
                        {
                            "description": "城市街道",
                            "entities": ["行人", "汽车"],
                            "image_style": "photorealistic",
                        },
                        {
                            "description": "公园场景",
                            "entities": ["树木", "长椅"],
                            "image_style": "photorealistic",
                        },
                    ],
                    "question_types": ["descriptive", "counting"],
                    "answer_style": "brief",
                    "constraints": {"min_entities": 2, "language": "zh"},
                },
            ]
        }
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        )
        yaml.dump(config, f, allow_unicode=True)
        f.flush()
        f.close()
        return f.name

    def test_generate_from_config(self):
        """测试从配置文件生成种子。"""
        path = self._write_vlm_config()
        try:
            engine = VisualSeedEngine()
            seeds = engine.generate_from_config(path)
            # 2 scenes × 2 question_types = 4 seeds
            assert len(seeds) == 4
            assert all(isinstance(s, VisualSeed) for s in seeds)
        finally:
            os.unlink(path)

    def test_max_seeds_limit(self):
        """测试 max_seeds 限制。"""
        path = self._write_vlm_config()
        try:
            engine = VisualSeedEngine()
            seeds = engine.generate_from_config(path, max_seeds=2)
            assert len(seeds) == 2
        finally:
            os.unlink(path)

    def test_seed_fields(self):
        """测试生成的种子字段完整性。"""
        path = self._write_vlm_config()
        try:
            engine = VisualSeedEngine()
            seeds = engine.generate_from_config(path, max_seeds=1)
            seed = seeds[0]
            assert seed.task_category == "scene_understanding"
            assert seed.scene_description in ("城市街道", "公园场景")
            assert len(seed.entities) >= 2
            assert seed.question_type in ("descriptive", "counting")
        finally:
            os.unlink(path)

    def test_generate_single(self):
        """测试生成单个种子。"""
        engine = VisualSeedEngine()
        seed = engine.generate_single(
            task_category="object_recognition",
            scene={"description": "桌面场景", "entities": ["杯子", "键盘"]},
            question_type="identification",
        )
        assert isinstance(seed, VisualSeed)
        assert seed.task_category == "object_recognition"

    def test_file_not_found(self):
        """测试配置文件不存在时抛出异常。"""
        engine = VisualSeedEngine()
        with pytest.raises(FileNotFoundError):
            engine.generate_from_config("/nonexistent/path.yaml")

    def test_empty_config(self):
        """测试空配置返回空列表。"""
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        )
        yaml.dump({"vlm_tasks": []}, f)
        f.flush()
        f.close()
        try:
            engine = VisualSeedEngine()
            seeds = engine.generate_from_config(f.name)
            assert seeds == []
        finally:
            os.unlink(f.name)


# =====================================================================
# SchemaVerifier 测试
# =====================================================================

class TestSchemaVerifier:
    """SchemaVerifier 单元测试。"""

    def test_valid_sample(self):
        """测试合法样本通过校验。"""
        verifier = SchemaVerifier()
        sample = _make_vlm_sample()
        result = verifier.verify(sample)
        assert result.passed is True
        assert result.stage == "schema"
        assert result.score == 1.0

    def test_empty_question(self):
        """测试空问题不通过。"""
        verifier = SchemaVerifier()
        sample = _make_vlm_sample(question="")
        result = verifier.verify(sample)
        assert result.passed is False

    def test_question_no_question_mark(self):
        """测试问题不以问号结尾不通过。"""
        verifier = SchemaVerifier()
        sample = _make_vlm_sample(question="描述图中的场景")
        result = verifier.verify(sample)
        assert result.passed is False
        assert "问号" in result.reason or "?" in result.reason

    def test_empty_answer(self):
        """测试空答案不通过。"""
        verifier = SchemaVerifier()
        sample = _make_vlm_sample(answer="")
        result = verifier.verify(sample)
        assert result.passed is False

    def test_empty_image_prompt(self):
        """测试空图像提示词不通过。"""
        verifier = SchemaVerifier()
        sample = _make_vlm_sample(image_prompt="")
        result = verifier.verify(sample)
        assert result.passed is False

    def test_chinese_image_prompt(self):
        """测试中文图像提示词不通过（应为英文）。"""
        verifier = SchemaVerifier()
        sample = _make_vlm_sample(image_prompt="城市街道上有两辆汽车")
        result = verifier.verify(sample)
        assert result.passed is False

    def test_empty_statement(self):
        """测试空语义陈述不通过。"""
        verifier = SchemaVerifier()
        sample = _make_vlm_sample(statement="")
        result = verifier.verify(sample)
        assert result.passed is False

    def test_batch_verify(self):
        """测试批量校验。"""
        verifier = SchemaVerifier()
        samples = [_make_vlm_sample(), _make_vlm_sample(question="")]
        results = verifier.verify_batch(samples)
        assert len(results) == 2
        assert results[0].passed is True
        assert results[1].passed is False


# =====================================================================
# VLMDatasetAdapter 测试
# =====================================================================

class TestVLMDatasetAdapter:
    """VLMDatasetAdapter 单元测试。"""

    def test_export_training_jsonl(self):
        """测试训练数据 JSONL 导出。"""
        adapter = VLMDatasetAdapter()
        records = [_make_vlm_record(), _make_vlm_record()]

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "train.jsonl")
            summary = adapter.export_training(records, path)
            assert summary.format == "jsonl"
            assert summary.verified_count == 2
            assert os.path.exists(path)

            # 验证 JSONL 格式
            with open(path, "r") as f:
                lines = f.readlines()
            assert len(lines) == 2
            for line in lines:
                obj = json.loads(line)
                assert "messages" in obj
                assert "images" in obj

    def test_export_training_filters_rejected(self):
        """测试训练导出过滤被拒绝的记录。"""
        adapter = VLMDatasetAdapter()
        records = [
            _make_vlm_record(),
            _make_vlm_record(label_quality="synthetic_rejected"),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "train.jsonl")
            summary = adapter.export_training(records, path)
            assert summary.verified_count == 1
            assert summary.rejected_count == 1

    def test_export_review_excel(self):
        """测试审阅报告 Excel 导出。"""
        adapter = VLMDatasetAdapter()
        records = [_make_vlm_record()]

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "review.xlsx")
            summary = adapter.export_review(records, path)
            assert summary.format == "xlsx"
            assert os.path.exists(path)

    def test_export_all(self):
        """测试同时导出训练数据和审阅报告。"""
        adapter = VLMDatasetAdapter()
        records = [_make_vlm_record()]

        with tempfile.TemporaryDirectory() as tmpdir:
            summaries = adapter.export_all(records, tmpdir, run_id="test")
            assert "training" in summaries
            assert "review" in summaries
            assert os.path.exists(summaries["training"].output_path)
            assert os.path.exists(summaries["review"].output_path)

    def test_export_empty_records(self):
        """测试空记录列表导出。"""
        adapter = VLMDatasetAdapter()

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "train.jsonl")
            summary = adapter.export_training([], path)
            assert summary.verified_count == 0
            assert os.path.exists(path)

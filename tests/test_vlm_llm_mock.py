"""
VLM 视觉链路 — LLM / API 相关模块的 Mock 测试。

覆盖：ImageClient、VLMClient、VisualGeneralizationEngine、
       ConsistencyVerifier、VisionConsistencyVerifier、
       ImageSynthesisCoordinator、VLMPipelineRunner
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.contracts import VisualSeed, VLMSample, VLMRecord, LabelQuality
from core.rule_verifier import StageResult
from core.image_client import ImageClient, ImageResult
from core.vlm_client import VLMClient, VLMJudgment
from core.visual_generalization_engine import VisualGeneralizationEngine
from core.consistency_verifier import ConsistencyVerifier
from core.vision_consistency_verifier import VisionConsistencyVerifier
from core.image_synthesis_coordinator import ImageSynthesisCoordinator
from core.vlm_pipeline_runner import (
    VLMPipelineRunner,
    PipelineResult,
    BatchPipelineResult,
)


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


# =====================================================================
# ImageClient Mock 测试
# =====================================================================

class TestImageClient:
    """ImageClient Mock 测试。"""

    def test_generate_success(self):
        """测试图像生成成功。"""
        import base64
        fake_image_data = base64.b64encode(b"fake_png_data").decode()
        mock_openai = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [MagicMock()]
        mock_response.data[0].b64_json = fake_image_data
        mock_openai.images.generate.return_value = mock_response

        with tempfile.TemporaryDirectory() as tmpdir:
            client = ImageClient(model="dall-e-3", max_retries=1, retry_delay=0.01)
            client._client = mock_openai  # 直接注入 Mock 客户端
            result = client.generate(
                prompt="A city intersection",
                output_dir=tmpdir,
            )
            assert result.success is True
            assert result.image_path is not None
            assert os.path.exists(result.image_path)
            assert result.model == "dall-e-3"

    def test_generate_api_failure(self):
        """测试 API 调用失败时返回失败结果。"""
        mock_openai = MagicMock()
        mock_openai.images.generate.side_effect = Exception("API error")

        with tempfile.TemporaryDirectory() as tmpdir:
            client = ImageClient(model="dall-e-3", max_retries=1, retry_delay=0.01)
            client._client = mock_openai
            result = client.generate(
                prompt="A city intersection",
                output_dir=tmpdir,
            )
            assert result.success is False
            assert result.error is not None

    def test_generate_batch(self):
        """测试批量图像生成。"""
        import base64
        fake_image_data = base64.b64encode(b"fake_png_data").decode()
        mock_openai = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [MagicMock()]
        mock_response.data[0].b64_json = fake_image_data
        mock_openai.images.generate.return_value = mock_response

        with tempfile.TemporaryDirectory() as tmpdir:
            client = ImageClient(model="dall-e-3", max_retries=1, retry_delay=0.01)
            client._client = mock_openai
            results = client.generate_batch(
                prompts=["prompt1", "prompt2"],
                output_dir=tmpdir,
            )
            assert len(results) == 2
            assert all(r.success for r in results)


# =====================================================================
# VLMClient Mock 测试
# =====================================================================

class TestVLMClient:
    """VLMClient Mock 测试。"""

    def _make_mock_openai(self, content: str):
        """创建 Mock OpenAI 客户端。"""
        mock_openai = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = content
        mock_response.usage.total_tokens = 200
        mock_openai.chat.completions.create.return_value = mock_response
        return mock_openai

    def test_judge_success(self):
        """测试 judge 方法成功。"""
        mock_openai = self._make_mock_openai(json.dumps({
            "score": 0.85, "passed": True, "reason": "图像与问答一致",
        }))

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"fake_png_data")
            img_path = f.name

        try:
            client = VLMClient(model="gpt-4.1-mini", max_retries=1, retry_delay=0.01)
            client._client = mock_openai
            judgment = client.judge(
                image_path=img_path,
                question="图中有几辆汽车？",
                expected_answer="两辆",
                threshold=0.7,
            )
            assert judgment.passed is True
            assert judgment.score == 0.85
        finally:
            os.unlink(img_path)

    def test_judge_consistency_success(self):
        """测试 judge_consistency 方法成功。"""
        mock_openai = self._make_mock_openai(json.dumps({
            "score": 0.9, "passed": True, "reason": "陈述与图像一致",
        }))

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"fake_png_data")
            img_path = f.name

        try:
            client = VLMClient(model="gpt-4.1-mini", max_retries=1, retry_delay=0.01)
            client._client = mock_openai
            judgment = client.judge_consistency(
                image_path=img_path,
                statement="图中包含两辆汽车",
                threshold=0.7,
            )
            assert judgment.passed is True
            assert judgment.score == 0.9
        finally:
            os.unlink(img_path)

    def test_judge_file_not_found(self):
        """测试图像文件不存在时抛出异常。"""
        client = VLMClient(model="gpt-4.1-mini")
        with pytest.raises(FileNotFoundError):
            client.judge(
                image_path="/nonexistent/image.png",
                question="test",
                expected_answer="test",
            )

    def test_judge_parse_failure_fallback(self):
        """测试 JSON 解析失败时的降级处理。"""
        mock_openai = self._make_mock_openai("This is not JSON at all")

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"fake_png_data")
            img_path = f.name

        try:
            client = VLMClient(model="gpt-4.1-mini", max_retries=1, retry_delay=0.01)
            client._client = mock_openai
            judgment = client.judge(
                image_path=img_path,
                question="test",
                expected_answer="test",
            )
            assert judgment.passed is False
        finally:
            os.unlink(img_path)


# =====================================================================
# VisualGeneralizationEngine Mock 测试
# =====================================================================

class TestVisualGeneralizationEngine:
    """VisualGeneralizationEngine Mock 测试。"""

    def test_generate_success(self):
        """测试正常生成候选样本。"""
        mock_llm = MagicMock()
        mock_llm.chat_json.return_value = {
            "samples": [
                {
                    "question": "图中有几辆汽车？",
                    "answer": "图中有两辆汽车。",
                    "image_prompt": "A city intersection with two cars",
                    "statement": "图中包含两辆汽车",
                }
            ]
        }

        engine = VisualGeneralizationEngine(llm_client=mock_llm)
        seed = _make_visual_seed()
        samples = engine.generate(seed, count=1)

        assert len(samples) == 1
        assert samples[0].question == "图中有几辆汽车？"
        assert samples[0].seed_id == seed.seed_id
        assert samples[0].status == "pending"
        mock_llm.chat_json.assert_called_once()

    def test_generate_multiple(self):
        """测试生成多个候选样本。"""
        mock_llm = MagicMock()
        mock_llm.chat_json.return_value = {
            "samples": [
                {
                    "question": "图中有几辆汽车？",
                    "answer": "两辆",
                    "image_prompt": "Two cars at intersection",
                    "statement": "两辆汽车",
                },
                {
                    "question": "行人在做什么？",
                    "answer": "行人在过马路",
                    "image_prompt": "Pedestrians crossing the street",
                    "statement": "行人正在过马路",
                },
            ]
        }

        engine = VisualGeneralizationEngine(llm_client=mock_llm)
        seed = _make_visual_seed()
        samples = engine.generate(seed, count=2)

        assert len(samples) == 2

    def test_generate_empty_scene_raises(self):
        """测试空场景描述抛出 ValueError。"""
        mock_llm = MagicMock()
        engine = VisualGeneralizationEngine(llm_client=mock_llm)
        seed = _make_visual_seed(scene_description="")

        with pytest.raises(ValueError, match="场景描述不能为空"):
            engine.generate(seed)

    def test_generate_llm_failure(self):
        """测试 LLM 调用失败时抛出异常。"""
        mock_llm = MagicMock()
        mock_llm.chat_json.side_effect = RuntimeError("LLM API timeout")

        engine = VisualGeneralizationEngine(llm_client=mock_llm)
        seed = _make_visual_seed()

        with pytest.raises(RuntimeError, match="LLM API timeout"):
            engine.generate(seed)

    def test_generate_batch_with_failure(self):
        """测试批量生成中部分失败。"""
        mock_llm = MagicMock()
        # 第一次成功，第二次失败
        mock_llm.chat_json.side_effect = [
            {
                "samples": [
                    {
                        "question": "Q1？",
                        "answer": "A1",
                        "image_prompt": "prompt1",
                        "statement": "S1",
                    }
                ]
            },
            RuntimeError("API error"),
        ]

        engine = VisualGeneralizationEngine(llm_client=mock_llm)
        seeds = [_make_visual_seed(), _make_visual_seed()]
        samples = engine.generate_batch(seeds, count=1)

        # 应有 2 个样本：1 个成功 + 1 个失败
        assert len(samples) == 2
        assert samples[0].status == "pending"
        assert samples[1].status == "failed"

    def test_parse_items_key(self):
        """测试解析 items 键（替代 samples 键）。"""
        mock_llm = MagicMock()
        mock_llm.chat_json.return_value = {
            "items": [
                {
                    "question": "Q？",
                    "answer": "A",
                    "image_prompt": "prompt",
                    "statement": "S",
                }
            ]
        }

        engine = VisualGeneralizationEngine(llm_client=mock_llm)
        seed = _make_visual_seed()
        samples = engine.generate(seed)
        assert len(samples) == 1


# =====================================================================
# ConsistencyVerifier Mock 测试
# =====================================================================

class TestConsistencyVerifier:
    """ConsistencyVerifier Mock 测试。"""

    def test_verify_pass(self):
        """测试文本自洽校验通过。"""
        mock_llm = MagicMock()
        mock_llm.chat_json.return_value = {
            "score": 0.85,
            "passed": True,
            "reason": "文本一致",
            "dimensions": {
                "qa_consistency": 0.9,
                "prompt_relevance": 0.8,
                "statement_logic": 0.85,
            },
        }

        verifier = ConsistencyVerifier(llm_client=mock_llm)
        sample = _make_vlm_sample()
        result = verifier.verify(sample)

        assert result.passed is True
        assert result.score == 0.85
        assert result.stage == "consistency"

    def test_verify_fail(self):
        """测试文本自洽校验不通过。"""
        mock_llm = MagicMock()
        mock_llm.chat_json.return_value = {
            "score": 0.3,
            "passed": False,
            "reason": "问题与答案不一致",
        }

        verifier = ConsistencyVerifier(llm_client=mock_llm)
        sample = _make_vlm_sample()
        result = verifier.verify(sample)

        assert result.passed is False
        assert result.score == 0.3

    def test_verify_llm_failure(self):
        """测试 LLM 调用失败时返回失败结果。"""
        mock_llm = MagicMock()
        mock_llm.chat_json.side_effect = RuntimeError("API error")

        verifier = ConsistencyVerifier(llm_client=mock_llm)
        sample = _make_vlm_sample()
        result = verifier.verify(sample)

        assert result.passed is False
        assert "LLM 调用失败" in result.reason

    def test_verify_batch(self):
        """测试批量文本自洽校验。"""
        mock_llm = MagicMock()
        mock_llm.chat_json.return_value = {
            "score": 0.85,
            "passed": True,
            "reason": "OK",
        }

        verifier = ConsistencyVerifier(llm_client=mock_llm)
        samples = [_make_vlm_sample(), _make_vlm_sample()]
        results = verifier.verify_batch(samples)

        assert len(results) == 2
        assert all(r.passed for r in results)

    def test_verify_custom_threshold(self):
        """测试自定义阈值。"""
        mock_llm = MagicMock()
        mock_llm.chat_json.return_value = {
            "score": 0.6,
            "passed": False,
            "reason": "低于阈值",
        }

        verifier = ConsistencyVerifier(llm_client=mock_llm, default_threshold=0.5)
        sample = _make_vlm_sample()
        result = verifier.verify(sample, threshold=0.8)

        assert result.passed is False


# =====================================================================
# VisionConsistencyVerifier Mock 测试
# =====================================================================

class TestVisionConsistencyVerifier:
    """VisionConsistencyVerifier Mock 测试。"""

    def test_verify_pass(self):
        """测试视觉一致性校验通过。"""
        mock_vlm = MagicMock()
        mock_vlm.judge.return_value = VLMJudgment(
            passed=True, score=0.9, reason="QA 一致", model="gpt-4.1-mini"
        )
        mock_vlm.judge_consistency.return_value = VLMJudgment(
            passed=True, score=0.85, reason="陈述一致", model="gpt-4.1-mini"
        )

        verifier = VisionConsistencyVerifier(vlm_client=mock_vlm)

        # 创建临时图像文件使 has_image 为 True
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"fake")
            img_path = f.name

        try:
            sample = _make_vlm_sample()
            sample.image_path = img_path
            result = verifier.verify(sample)

            assert result.passed is True
            assert result.stage == "vision_consistency"
            # 综合分数 = 0.9 * 0.6 + 0.85 * 0.4 = 0.54 + 0.34 = 0.88
            assert abs(result.score - 0.88) < 0.01
        finally:
            os.unlink(img_path)

    def test_verify_no_image(self):
        """测试无图像时返回失败。"""
        mock_vlm = MagicMock()
        verifier = VisionConsistencyVerifier(vlm_client=mock_vlm)

        sample = _make_vlm_sample()
        # sample.image_path 默认为空
        result = verifier.verify(sample)

        assert result.passed is False
        mock_vlm.judge.assert_not_called()

    def test_verify_below_threshold(self):
        """测试低于阈值时不通过。"""
        mock_vlm = MagicMock()
        mock_vlm.judge.return_value = VLMJudgment(
            passed=False, score=0.3, reason="不一致", model="gpt-4.1-mini"
        )
        mock_vlm.judge_consistency.return_value = VLMJudgment(
            passed=False, score=0.2, reason="不一致", model="gpt-4.1-mini"
        )

        verifier = VisionConsistencyVerifier(vlm_client=mock_vlm, default_threshold=0.7)

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"fake")
            img_path = f.name

        try:
            sample = _make_vlm_sample()
            sample.image_path = img_path
            result = verifier.verify(sample)

            assert result.passed is False
            # 综合分数 = 0.3 * 0.6 + 0.2 * 0.4 = 0.26
            assert result.score < 0.7
        finally:
            os.unlink(img_path)

    def test_verify_vlm_failure(self):
        """测试 VLM 调用失败时返回失败结果。"""
        mock_vlm = MagicMock()
        mock_vlm.judge.side_effect = RuntimeError("VLM API error")

        verifier = VisionConsistencyVerifier(vlm_client=mock_vlm)

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"fake")
            img_path = f.name

        try:
            sample = _make_vlm_sample()
            sample.image_path = img_path
            result = verifier.verify(sample)

            assert result.passed is False
        finally:
            os.unlink(img_path)


# =====================================================================
# ImageSynthesisCoordinator Mock 测试
# =====================================================================

class TestImageSynthesisCoordinator:
    """ImageSynthesisCoordinator Mock 测试。"""

    def test_synthesize_success(self):
        """测试图像合成成功。"""
        mock_image_client = MagicMock()
        mock_image_client.generate.return_value = ImageResult(
            success=True,
            image_path="/tmp/output/test.png",
            prompt="test prompt",
            model="dall-e-3",
            resolution="1024x1024",
            generation_time_ms=1500,
        )

        coordinator = ImageSynthesisCoordinator(image_client=mock_image_client)
        sample = _make_vlm_sample()

        with tempfile.TemporaryDirectory() as tmpdir:
            result = coordinator.synthesize(sample, tmpdir)

        assert result.status == "image_generated"
        assert result.image_path == "/tmp/output/test.png"

    def test_synthesize_failure(self):
        """测试图像合成失败。"""
        mock_image_client = MagicMock()
        mock_image_client.generate.return_value = ImageResult(
            success=False,
            prompt="test prompt",
            error="API quota exceeded",
        )

        coordinator = ImageSynthesisCoordinator(image_client=mock_image_client)
        sample = _make_vlm_sample()

        with tempfile.TemporaryDirectory() as tmpdir:
            result = coordinator.synthesize(sample, tmpdir)

        assert result.status == "failed"
        assert "图像生成失败" in result.failure_reason

    def test_synthesize_no_prompt_raises(self):
        """测试无 image_prompt 时抛出 ValueError。"""
        mock_image_client = MagicMock()
        coordinator = ImageSynthesisCoordinator(image_client=mock_image_client)
        sample = _make_vlm_sample(image_prompt="")

        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValueError, match="缺少 image_prompt"):
                coordinator.synthesize(sample, tmpdir)

    def test_synthesize_batch_skip_failed(self):
        """测试批量合成跳过已失败样本。"""
        mock_image_client = MagicMock()
        mock_image_client.generate.return_value = ImageResult(
            success=True,
            image_path="/tmp/test.png",
            prompt="prompt",
            model="dall-e-3",
        )

        coordinator = ImageSynthesisCoordinator(image_client=mock_image_client)

        sample_ok = _make_vlm_sample()
        sample_failed = _make_vlm_sample()
        sample_failed.status = "failed"

        with tempfile.TemporaryDirectory() as tmpdir:
            results = coordinator.synthesize_batch(
                [sample_ok, sample_failed], tmpdir
            )

        assert len(results) == 2
        assert results[0].status == "image_generated"
        assert results[1].status == "failed"
        # 只调用了一次 generate（跳过了失败样本）
        assert mock_image_client.generate.call_count == 1


# =====================================================================
# VLMPipelineRunner Mock 测试
# =====================================================================

class TestVLMPipelineRunner:
    """VLMPipelineRunner Mock 测试。"""

    def _make_runner(
        self,
        gen_samples=None,
        img_success=True,
        schema_pass=True,
        consistency_pass=True,
        vision_pass=True,
    ):
        """创建带 Mock 依赖的管线运行器。"""
        seed = _make_visual_seed()

        # Mock 泛化引擎
        mock_gen = MagicMock()
        if gen_samples is None:
            sample = _make_vlm_sample(seed_id=seed.seed_id)
            gen_samples = [sample]
        mock_gen.generate.return_value = gen_samples

        # Mock 图像合成协调器
        mock_img = MagicMock()
        def synthesize_batch(samples, output_dir):
            for s in samples:
                if s.status != "failed":
                    if img_success:
                        s.image_path = "/tmp/test.png"
                        s.status = "image_generated"
                    else:
                        s.status = "failed"
                        s.failure_reason = "图像生成失败"
            return samples
        mock_img.synthesize_batch.side_effect = synthesize_batch

        # Mock 结构校验器
        mock_schema = MagicMock()
        mock_schema.verify.return_value = StageResult(
            stage="schema",
            passed=schema_pass,
            score=1.0 if schema_pass else 0.0,
            reason="OK" if schema_pass else "结构校验失败",
        )

        # Mock 文本自洽校验器
        mock_consistency = MagicMock()
        mock_consistency.verify.return_value = StageResult(
            stage="consistency",
            passed=consistency_pass,
            score=0.85 if consistency_pass else 0.3,
            reason="OK" if consistency_pass else "文本不一致",
        )

        # Mock 视觉一致性校验器
        mock_vision = MagicMock()
        mock_vision.verify.return_value = StageResult(
            stage="vision_consistency",
            passed=vision_pass,
            score=0.88 if vision_pass else 0.2,
            reason="OK" if vision_pass else "视觉不一致",
        )

        runner = VLMPipelineRunner(
            generalization_engine=mock_gen,
            image_coordinator=mock_img,
            schema_verifier=mock_schema,
            consistency_verifier=mock_consistency,
            vision_verifier=mock_vision,
        )

        return runner, seed

    def test_full_pipeline_all_pass(self):
        """测试完整管线全部通过。"""
        runner, seed = self._make_runner()
        result = runner.run_single(seed, "/tmp/output", run_id="test_run")

        assert isinstance(result, PipelineResult)
        assert result.total_generated == 1
        assert result.total_verified == 1
        assert result.total_rejected == 0
        assert result.total_failed == 0
        assert len(result.records) == 1
        assert result.records[0].run_id == "test_run"

    def test_schema_failure_short_circuits(self):
        """测试结构校验失败时短路。"""
        runner, seed = self._make_runner(schema_pass=False)
        result = runner.run_single(seed, "/tmp/output")

        assert result.total_rejected == 1
        assert result.total_verified == 0
        assert len(result.records) == 0

    def test_consistency_failure_short_circuits(self):
        """测试文本自洽校验失败时短路。"""
        runner, seed = self._make_runner(consistency_pass=False)
        result = runner.run_single(seed, "/tmp/output")

        assert result.total_rejected == 1
        assert result.total_verified == 0

    def test_vision_failure_rejects(self):
        """测试视觉一致性校验失败时拒绝。"""
        runner, seed = self._make_runner(vision_pass=False)
        result = runner.run_single(seed, "/tmp/output")

        assert result.total_rejected == 1
        assert result.total_verified == 0

    def test_image_generation_failure(self):
        """测试图像生成失败。"""
        runner, seed = self._make_runner(img_success=False)
        result = runner.run_single(seed, "/tmp/output")

        assert result.total_failed == 1
        assert result.total_verified == 0

    def test_generalization_failure(self):
        """测试泛化引擎失败时提前返回。"""
        mock_gen = MagicMock()
        mock_gen.generate.side_effect = RuntimeError("LLM error")

        runner = VLMPipelineRunner(generalization_engine=mock_gen)
        seed = _make_visual_seed()
        result = runner.run_single(seed, "/tmp/output")

        assert len(result.errors) > 0
        assert "文本泛化失败" in result.errors[0]

    def test_batch_pipeline(self):
        """测试批量管线。"""
        runner, seed = self._make_runner()
        seeds = [_make_visual_seed(), _make_visual_seed()]

        batch_result = runner.run_batch(seeds, "/tmp/output", run_id="batch_test")

        assert isinstance(batch_result, BatchPipelineResult)
        assert batch_result.total_seeds == 2
        assert batch_result.total_verified == 2
        assert batch_result.total_records == 2
        assert batch_result.run_id == "batch_test"

    def test_pipeline_result_to_dict(self):
        """测试 PipelineResult 序列化。"""
        runner, seed = self._make_runner()
        result = runner.run_single(seed, "/tmp/output", run_id="test")

        d = result.to_dict()
        assert "seed_id" in d
        assert "total_generated" in d
        assert "records" in d

    def test_batch_result_to_dict(self):
        """测试 BatchPipelineResult 序列化。"""
        runner, seed = self._make_runner()
        batch_result = runner.run_batch(
            [_make_visual_seed()], "/tmp/output", run_id="test"
        )

        d = batch_result.to_dict()
        assert "run_id" in d
        assert "total_seeds" in d
        assert "total_records" in d

    def test_confidence_score_calculation(self):
        """测试综合置信度计算。"""
        runner, seed = self._make_runner()
        result = runner.run_single(seed, "/tmp/output")

        # 三层验证分数: schema=1.0, consistency=0.85, vision=0.88
        # 平均置信度 = (1.0 + 0.85 + 0.88) / 3 ≈ 0.91
        record = result.records[0]
        assert record.confidence_score > 0.0

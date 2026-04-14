"""
Car-ORBIT-Agent — LLM 相关模块的 Mock 测试。

覆盖 LLMClient、GeneralizationEngine、SemanticVerifier、SafetyVerifier
以及 ProvenanceTracker 和 CascadeOrchestrator 的未覆盖分支。
"""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# ---------------------------------------------------------------------------
# 确保 core 可导入
# ---------------------------------------------------------------------------
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.seed_engine import Seed
from core.rule_verifier import StageResult
from core.llm_client import LLMClient
from core.generalization_engine import GeneralizationEngine, GeneralizationResult, ALL_DIMENSIONS
from core.semantic_verifier import SemanticVerifier
from core.safety_verifier import SafetyVerifier
from core.cascade_orchestrator import CascadeOrchestrator, VerificationResult
from core.provenance_tracker import ProvenanceTracker, OrbitRecord


# ---------------------------------------------------------------------------
# 辅助工具
# ---------------------------------------------------------------------------

def _make_seed(**overrides) -> Seed:
    """创建测试用种子。"""
    defaults = {
        "seed_id": "test_seed_001",
        "domain": "音乐",
        "function": "播放音乐",
        "sub_function": "按歌曲名播放",
        "standard_utterance": "播放晴天",
        "params": {"歌曲名": "晴天"},
        "source_type": "config",
    }
    defaults.update(overrides)
    return Seed(**defaults)


# ===========================================================================
# TestLLMClient
# ===========================================================================

class TestLLMClient:
    """LLMClient 的 Mock 测试。"""

    @patch("core.llm_client.OpenAI")
    def test_chat_success(self, mock_openai_cls):
        """测试正常的 chat 调用。"""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "帮我放首晴天"
        mock_response.usage.total_tokens = 100
        mock_client.chat.completions.create.return_value = mock_response

        llm = LLMClient(model="gpt-4.1-mini", max_retries=2, retry_delay=0.01)
        result = llm.chat([{"role": "user", "content": "test"}])

        assert result == "帮我放首晴天"
        assert llm.call_count == 1

    @patch("core.llm_client.OpenAI")
    def test_chat_retry_then_success(self, mock_openai_cls):
        """测试重试后成功。"""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "成功"
        mock_response.usage.total_tokens = 50

        # 第一次失败，第二次成功
        mock_client.chat.completions.create.side_effect = [
            Exception("API timeout"),
            mock_response,
        ]

        llm = LLMClient(model="gpt-4.1-mini", max_retries=3, retry_delay=0.01)
        result = llm.chat([{"role": "user", "content": "test"}])

        assert result == "成功"
        assert llm.call_count == 1
        assert mock_client.chat.completions.create.call_count == 2

    @patch("core.llm_client.OpenAI")
    def test_chat_all_retries_fail(self, mock_openai_cls):
        """测试所有重试都失败后抛出 RuntimeError。"""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("persistent error")

        llm = LLMClient(model="gpt-4.1-mini", max_retries=2, retry_delay=0.01)

        with pytest.raises(RuntimeError, match="重试后仍然失败"):
            llm.chat([{"role": "user", "content": "test"}])

    @patch("core.llm_client.OpenAI")
    def test_chat_json_success(self, mock_openai_cls):
        """测试 chat_json 正常解析。"""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"score": 0.9, "reason": "good"}'
        mock_response.usage.total_tokens = 80
        mock_client.chat.completions.create.return_value = mock_response

        llm = LLMClient(model="gpt-4.1-mini", retry_delay=0.01)
        result = llm.chat_json([{"role": "system", "content": "test"}, {"role": "user", "content": "q"}])

        assert result["score"] == 0.9
        assert result["reason"] == "good"

    @patch("core.llm_client.OpenAI")
    def test_chat_json_with_code_block(self, mock_openai_cls):
        """测试 chat_json 从 markdown 代码块中提取 JSON。"""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '```json\n{"score": 0.8}\n```'
        mock_response.usage.total_tokens = 60
        mock_client.chat.completions.create.return_value = mock_response

        llm = LLMClient(retry_delay=0.01)
        result = llm.chat_json([{"role": "user", "content": "q"}])
        assert result["score"] == 0.8

    @patch("core.llm_client.OpenAI")
    def test_chat_json_extract_object(self, mock_openai_cls):
        """测试 chat_json 从混合文本中提取 JSON 对象。"""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = 'Here is the result: {"key": "value"} done.'
        mock_response.usage.total_tokens = 60
        mock_client.chat.completions.create.return_value = mock_response

        llm = LLMClient(retry_delay=0.01)
        result = llm.chat_json([{"role": "user", "content": "q"}])
        assert result["key"] == "value"

    @patch("core.llm_client.OpenAI")
    def test_chat_json_extract_array(self, mock_openai_cls):
        """测试 chat_json 从数组响应中提取。"""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = 'Result: [1, 2, 3]'
        mock_response.usage.total_tokens = 60
        mock_client.chat.completions.create.return_value = mock_response

        llm = LLMClient(retry_delay=0.01)
        result = llm.chat_json([{"role": "user", "content": "q"}])
        assert result["items"] == [1, 2, 3]

    @patch("core.llm_client.OpenAI")
    def test_chat_json_invalid_raises(self, mock_openai_cls):
        """测试 chat_json 无法解析时抛出异常。"""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "This is not JSON at all"
        mock_response.usage.total_tokens = 30
        mock_client.chat.completions.create.return_value = mock_response

        llm = LLMClient(retry_delay=0.01)
        with pytest.raises(json.JSONDecodeError):
            llm.chat_json([{"role": "user", "content": "q"}])

    @patch("core.llm_client.OpenAI")
    def test_chat_json_no_system_prompt(self, mock_openai_cls):
        """测试 chat_json 在没有 system prompt 时注入 JSON 格式要求。"""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"ok": true}'
        mock_response.usage.total_tokens = 40
        mock_client.chat.completions.create.return_value = mock_response

        llm = LLMClient(retry_delay=0.01)
        result = llm.chat_json([{"role": "user", "content": "q"}])
        assert result["ok"] is True

        # 验证注入了 system prompt
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert "JSON" in messages[0]["content"]

    @patch("core.llm_client.OpenAI")
    def test_chat_custom_model(self, mock_openai_cls):
        """测试使用自定义模型覆盖默认模型。"""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "ok"
        mock_response.usage.total_tokens = 10
        mock_client.chat.completions.create.return_value = mock_response

        llm = LLMClient(model="gpt-4.1-mini", retry_delay=0.01)
        llm.chat([{"role": "user", "content": "test"}], model="gpt-4.1-nano")

        call_args = mock_client.chat.completions.create.call_args
        assert call_args.kwargs["model"] == "gpt-4.1-nano"


# ===========================================================================
# TestGeneralizationEngine
# ===========================================================================

class TestGeneralizationEngine:
    """GeneralizationEngine 的 Mock 测试。"""

    def test_generalize_success(self):
        """测试正常泛化流程。"""
        mock_llm = MagicMock()
        mock_llm.chat.return_value = "帮我放首晴天\n来首晴天吧\n播放一下晴天"

        engine = GeneralizationEngine(llm_client=mock_llm)
        seed = _make_seed()
        result = engine.generalize(seed, num_variants=3)

        assert isinstance(result, GeneralizationResult)
        assert len(result.variants) == 3
        assert result.dimensions_used == ALL_DIMENSIONS
        assert result.llm_model == "gpt-4.1-mini"

    def test_generalize_with_specific_dimensions(self):
        """测试指定部分维度。"""
        mock_llm = MagicMock()
        mock_llm.chat.return_value = "帮我放首晴天\n来首晴天吧"

        engine = GeneralizationEngine(llm_client=mock_llm)
        seed = _make_seed()
        result = engine.generalize(seed, num_variants=2, dimensions=["colloquial", "simplification"])

        assert result.dimensions_used == ["colloquial", "simplification"]
        assert len(result.variants) <= 2

    def test_generalize_invalid_dimension(self):
        """测试无效维度名称。"""
        mock_llm = MagicMock()
        engine = GeneralizationEngine(llm_client=mock_llm)
        seed = _make_seed()

        with pytest.raises(ValueError, match="无效的泛化维度"):
            engine.generalize(seed, dimensions=["invalid_dim"])

    def test_generalize_llm_failure(self):
        """测试 LLM 调用失败时返回空列表。"""
        mock_llm = MagicMock()
        mock_llm.chat.side_effect = RuntimeError("API error")

        engine = GeneralizationEngine(llm_client=mock_llm)
        seed = _make_seed()
        result = engine.generalize(seed, num_variants=3)

        assert result.variants == []

    def test_generalize_dedup(self):
        """测试变体去重。"""
        mock_llm = MagicMock()
        mock_llm.chat.return_value = "帮我放首晴天\n帮我放首晴天\n来首晴天吧"

        engine = GeneralizationEngine(llm_client=mock_llm)
        seed = _make_seed()
        result = engine.generalize(seed, num_variants=5)

        # 去重后应该只有 2 个
        assert len(result.variants) == 2

    def test_generalize_filters_standard_utterance(self):
        """测试过滤与标准话术完全相同的变体。"""
        mock_llm = MagicMock()
        mock_llm.chat.return_value = "播放晴天\n帮我放首晴天\n来首晴天吧"

        engine = GeneralizationEngine(llm_client=mock_llm)
        seed = _make_seed()
        result = engine.generalize(seed, num_variants=5)

        assert "播放晴天" not in result.variants
        assert len(result.variants) == 2

    def test_generalize_with_provenance_tracker(self):
        """测试泛化结果记录到追踪器。"""
        mock_llm = MagicMock()
        mock_llm.chat.return_value = "帮我放首晴天\n来首晴天吧"

        tracker = ProvenanceTracker()
        engine = GeneralizationEngine(llm_client=mock_llm, provenance_tracker=tracker)
        seed = _make_seed()
        engine.generalize(seed, num_variants=2)

        # 检查追踪器记录了泛化事件
        assert len(tracker._trace_lines) == 1
        assert tracker._trace_lines[0]["event"] == "generalization_completed"

    def test_generalize_batch(self):
        """测试批量泛化。"""
        mock_llm = MagicMock()
        mock_llm.chat.return_value = "变体A\n变体B"

        engine = GeneralizationEngine(llm_client=mock_llm)
        seeds = [_make_seed(seed_id=f"seed_{i}") for i in range(3)]
        results = engine.generalize_batch(seeds, num_variants=2)

        assert len(results) == 3
        assert all(isinstance(r, GeneralizationResult) for r in results)

    def test_generalize_parse_numbered_lines(self):
        """测试解析带编号的 LLM 响应。"""
        mock_llm = MagicMock()
        mock_llm.chat.return_value = '1. 帮我放首晴天\n2) 来首晴天吧\n3、播放一下晴天'

        engine = GeneralizationEngine(llm_client=mock_llm)
        seed = _make_seed()
        result = engine.generalize(seed, num_variants=3)

        assert len(result.variants) == 3

    def test_generalize_parse_quoted_lines(self):
        """测试解析带引号的 LLM 响应。"""
        mock_llm = MagicMock()
        mock_llm.chat.return_value = '"帮我放首晴天"\n"来首晴天吧"\n"播放一下晴天"'

        engine = GeneralizationEngine(llm_client=mock_llm)
        seed = _make_seed()
        result = engine.generalize(seed, num_variants=3)

        assert len(result.variants) == 3
        assert all('"' not in v for v in result.variants)

    def test_generalize_result_to_dict(self):
        """测试 GeneralizationResult.to_dict。"""
        seed = _make_seed()
        result = GeneralizationResult(
            seed=seed,
            variants=["v1", "v2"],
            generation_strategies=["s1", "s2"],
            dimensions_used=["colloquial"],
            llm_model="gpt-4.1-mini",
            timestamp="2026-01-01T00:00:00Z",
        )
        d = result.to_dict()
        assert d["variants"] == ["v1", "v2"]
        assert d["llm_model"] == "gpt-4.1-mini"
        assert "seed" in d

    def test_generalize_no_params_seed(self):
        """测试无参数种子的泛化。"""
        mock_llm = MagicMock()
        mock_llm.chat.return_value = "帮我开导航\n开一下导航"

        engine = GeneralizationEngine(llm_client=mock_llm)
        seed = _make_seed(standard_utterance="打开导航", params={})
        result = engine.generalize(seed, num_variants=2)

        assert len(result.variants) == 2


# ===========================================================================
# TestSemanticVerifier
# ===========================================================================

class TestSemanticVerifier:
    """SemanticVerifier 的 Mock 测试。"""

    def test_verify_pass(self):
        """测试语义验证通过。"""
        mock_llm = MagicMock()
        mock_llm.chat_json.return_value = {
            "semantic_consistency": 0.95,
            "naturalness": 0.9,
            "nlu_clarity": 0.88,
            "overall_score": 0.91,
            "reason": "语义高度一致",
        }

        verifier = SemanticVerifier(llm_client=mock_llm, threshold=0.7)
        seed = _make_seed()
        result = verifier.verify("帮我放首晴天", seed)

        assert isinstance(result, StageResult)
        assert result.passed is True
        assert result.score == 0.91
        assert result.stage == "semantic"

    def test_verify_fail(self):
        """测试语义验证失败。"""
        mock_llm = MagicMock()
        mock_llm.chat_json.return_value = {
            "semantic_consistency": 0.3,
            "naturalness": 0.4,
            "nlu_clarity": 0.2,
            "overall_score": 0.3,
            "reason": "语义偏移严重",
        }

        verifier = SemanticVerifier(llm_client=mock_llm, threshold=0.7)
        seed = _make_seed()
        result = verifier.verify("打开空调", seed)

        assert result.passed is False
        assert result.score == 0.3

    def test_verify_no_overall_score(self):
        """测试没有 overall_score 时从三个维度计算。"""
        mock_llm = MagicMock()
        mock_llm.chat_json.return_value = {
            "semantic_consistency": 0.9,
            "naturalness": 0.8,
            "nlu_clarity": 0.7,
            "reason": "不错",
        }

        verifier = SemanticVerifier(llm_client=mock_llm, threshold=0.7)
        seed = _make_seed()
        result = verifier.verify("帮我放首晴天", seed)

        # 0.9*0.4 + 0.8*0.3 + 0.7*0.3 = 0.36 + 0.24 + 0.21 = 0.81
        assert result.passed is True
        assert abs(result.score - 0.81) < 0.01

    def test_verify_llm_failure(self):
        """测试 LLM 调用失败时返回保守评分。"""
        mock_llm = MagicMock()
        mock_llm.chat_json.side_effect = RuntimeError("API error")

        verifier = SemanticVerifier(llm_client=mock_llm, threshold=0.7)
        seed = _make_seed()
        result = verifier.verify("帮我放首晴天", seed)

        assert result.passed is False
        assert result.score == 0.5
        assert "LLM 调用失败" in result.reason

    def test_verify_batch(self):
        """测试批量语义验证。"""
        mock_llm = MagicMock()
        mock_llm.chat_json.return_value = {
            "overall_score": 0.85,
            "reason": "ok",
        }

        verifier = SemanticVerifier(llm_client=mock_llm, threshold=0.7)
        seed = _make_seed()
        results = verifier.verify_batch(["变体1", "变体2", "变体3"], seed)

        assert len(results) == 3
        assert all(r.passed for r in results)

    def test_verify_empty_reason_generates_default(self):
        """测试空 reason 时生成默认描述。"""
        mock_llm = MagicMock()
        mock_llm.chat_json.return_value = {
            "overall_score": 0.85,
            "reason": "",
        }

        verifier = SemanticVerifier(llm_client=mock_llm, threshold=0.7)
        seed = _make_seed()
        result = verifier.verify("帮我放首晴天", seed)

        assert "语义分数" in result.reason
        assert "通过" in result.reason


# ===========================================================================
# TestSafetyVerifier
# ===========================================================================

class TestSafetyVerifier:
    """SafetyVerifier 的 Mock 测试。"""

    def test_verify_pass(self):
        """测试安全验证通过。"""
        mock_llm = MagicMock()
        mock_llm.chat_json.return_value = {
            "driving_safety": 1.0,
            "regulatory_compliance": 1.0,
            "privacy_safety": 1.0,
            "overall_score": 1.0,
            "risk_level": "low",
            "reason": "完全安全",
        }

        verifier = SafetyVerifier(llm_client=mock_llm, threshold=0.8)
        seed = _make_seed()
        result = verifier.verify("帮我放首晴天", seed)

        assert result.passed is True
        assert result.score == 1.0
        assert result.stage == "safety"

    def test_verify_fail_high_risk(self):
        """测试高风险变体验证失败。"""
        mock_llm = MagicMock()
        mock_llm.chat_json.return_value = {
            "driving_safety": 0.2,
            "regulatory_compliance": 0.5,
            "privacy_safety": 0.8,
            "overall_score": 0.4,
            "risk_level": "high",
            "reason": "可能导致驾驶分心",
        }

        verifier = SafetyVerifier(llm_client=mock_llm, threshold=0.8)
        seed = _make_seed()
        result = verifier.verify("播放视频", seed)

        assert result.passed is False
        assert result.score == 0.4

    def test_verify_no_overall_score(self):
        """测试没有 overall_score 时从三个维度计算。"""
        mock_llm = MagicMock()
        mock_llm.chat_json.return_value = {
            "driving_safety": 1.0,
            "regulatory_compliance": 0.9,
            "privacy_safety": 0.8,
            "risk_level": "low",
            "reason": "安全",
        }

        verifier = SafetyVerifier(llm_client=mock_llm, threshold=0.8)
        seed = _make_seed()
        result = verifier.verify("帮我放首晴天", seed)

        # 1.0*0.5 + 0.9*0.3 + 0.8*0.2 = 0.5 + 0.27 + 0.16 = 0.93
        assert result.passed is True
        assert abs(result.score - 0.93) < 0.01

    def test_verify_llm_failure(self):
        """测试 LLM 调用失败时返回保守评分。"""
        mock_llm = MagicMock()
        mock_llm.chat_json.side_effect = RuntimeError("API error")

        verifier = SafetyVerifier(llm_client=mock_llm, threshold=0.8)
        seed = _make_seed()
        result = verifier.verify("帮我放首晴天", seed)

        assert result.passed is False
        assert result.score == 0.5
        assert "LLM 调用失败" in result.reason

    def test_verify_batch(self):
        """测试批量安全验证。"""
        mock_llm = MagicMock()
        mock_llm.chat_json.return_value = {
            "overall_score": 0.95,
            "risk_level": "low",
            "reason": "安全",
        }

        verifier = SafetyVerifier(llm_client=mock_llm, threshold=0.8)
        seed = _make_seed()
        results = verifier.verify_batch(["变体1", "变体2"], seed)

        assert len(results) == 2
        assert all(r.passed for r in results)

    def test_verify_empty_reason_generates_default(self):
        """测试空 reason 时生成默认描述。"""
        mock_llm = MagicMock()
        mock_llm.chat_json.return_value = {
            "overall_score": 0.95,
            "risk_level": "low",
            "reason": "",
        }

        verifier = SafetyVerifier(llm_client=mock_llm, threshold=0.8)
        seed = _make_seed()
        result = verifier.verify("帮我放首晴天", seed)

        assert "安全分数" in result.reason
        assert "通过" in result.reason


# ===========================================================================
# TestCascadeOrchestratorExtended
# ===========================================================================

class TestCascadeOrchestratorExtended:
    """CascadeOrchestrator 的扩展测试 — 覆盖 verify_batch 和 to_dict。"""

    def test_verify_batch(self):
        """测试批量级联验证。"""
        mock_rule = MagicMock()
        mock_rule.verify.return_value = StageResult(stage="rule", passed=True, score=1.0, reason="ok")

        mock_semantic = MagicMock()
        mock_semantic.verify.return_value = StageResult(stage="semantic", passed=True, score=0.9, reason="ok")

        mock_safety = MagicMock()
        mock_safety.verify.return_value = StageResult(stage="safety", passed=True, score=0.95, reason="ok")

        orchestrator = CascadeOrchestrator(
            rule_verifier=mock_rule,
            semantic_verifier=mock_semantic,
            safety_verifier=mock_safety,
        )

        seed = _make_seed()
        results = orchestrator.verify_batch(["变体1", "变体2", "变体3"], seed)

        assert len(results) == 3
        assert all(r.overall_passed for r in results)

    def test_safety_failure(self):
        """测试安全验证失败（规则和语义通过）。"""
        mock_rule = MagicMock()
        mock_rule.verify.return_value = StageResult(stage="rule", passed=True, score=1.0, reason="ok")

        mock_semantic = MagicMock()
        mock_semantic.verify.return_value = StageResult(stage="semantic", passed=True, score=0.9, reason="ok")

        mock_safety = MagicMock()
        mock_safety.verify.return_value = StageResult(stage="safety", passed=False, score=0.3, reason="危险")

        orchestrator = CascadeOrchestrator(
            rule_verifier=mock_rule,
            semantic_verifier=mock_semantic,
            safety_verifier=mock_safety,
        )

        seed = _make_seed()
        result = orchestrator.verify("播放视频", seed)

        assert result.overall_passed is False
        assert result.safety_check is not None
        assert result.safety_check.passed is False

    def test_verification_result_to_dict_all_stages(self):
        """测试 VerificationResult.to_dict 包含所有阶段。"""
        result = VerificationResult(
            variant="帮我放首晴天",
            rule_check=StageResult(stage="rule", passed=True, score=1.0, reason="ok"),
            semantic_check=StageResult(stage="semantic", passed=True, score=0.9, reason="ok"),
            safety_check=StageResult(stage="safety", passed=True, score=0.95, reason="ok"),
            overall_passed=True,
            confidence_score=0.92,
        )
        d = result.to_dict()

        assert d["overall_passed"] is True
        assert d["rule_check"]["passed"] is True
        assert d["semantic_check"]["passed"] is True
        assert d["safety_check"]["passed"] is True

    def test_verification_result_to_dict_skipped_stages(self):
        """测试 VerificationResult.to_dict 跳过的阶段显示 skipped。"""
        result = VerificationResult(
            variant="帮我放首晴天",
            rule_check=StageResult(stage="rule", passed=False, score=0.0, reason="too short"),
            semantic_check=None,
            safety_check=None,
            overall_passed=False,
            confidence_score=0.0,
        )
        d = result.to_dict()

        assert d["semantic_check"]["reason"] == "skipped"
        assert d["safety_check"]["reason"] == "skipped"

    def test_with_provenance_tracker(self):
        """测试级联验证结果记录到追踪器。"""
        mock_rule = MagicMock()
        mock_rule.verify.return_value = StageResult(stage="rule", passed=True, score=1.0, reason="ok")

        mock_semantic = MagicMock()
        mock_semantic.verify.return_value = StageResult(stage="semantic", passed=True, score=0.9, reason="ok")

        mock_safety = MagicMock()
        mock_safety.verify.return_value = StageResult(stage="safety", passed=True, score=0.95, reason="ok")

        tracker = ProvenanceTracker()
        orchestrator = CascadeOrchestrator(
            rule_verifier=mock_rule,
            semantic_verifier=mock_semantic,
            safety_verifier=mock_safety,
            provenance_tracker=tracker,
        )

        seed = _make_seed()
        orchestrator.verify("帮我放首晴天", seed)

        assert len(tracker._trace_lines) == 1
        assert tracker._trace_lines[0]["event"] == "verification_completed"


# ===========================================================================
# TestProvenanceTrackerExtended
# ===========================================================================

class TestProvenanceTrackerExtended:
    """ProvenanceTracker 的扩展测试 — 覆盖 record_seed、record_generalization、record_verification、save_trace、get_statistics。"""

    def test_record_seed(self):
        """测试记录种子事件。"""
        tracker = ProvenanceTracker()
        seed = _make_seed()
        tracker.record_seed(seed)

        assert len(tracker._trace_lines) == 1
        assert tracker._trace_lines[0]["event"] == "seed_generated"
        assert tracker._trace_lines[0]["seed_id"] == "test_seed_001"

    def test_record_generalization(self):
        """测试记录泛化事件。"""
        tracker = ProvenanceTracker()
        seed = _make_seed()
        tracker.record_generalization(seed, ["v1", "v2"], {"model": "gpt-4.1-mini"})

        assert len(tracker._trace_lines) == 1
        assert tracker._trace_lines[0]["event"] == "generalization_completed"
        assert tracker._trace_lines[0]["num_variants"] == 2

    def test_record_verification(self):
        """测试记录验证事件。"""
        tracker = ProvenanceTracker()
        seed = _make_seed()
        tracker.record_verification(seed, "帮我放首晴天", {
            "overall_passed": True,
            "confidence_score": 0.92,
        })

        assert len(tracker._trace_lines) == 1
        assert tracker._trace_lines[0]["event"] == "verification_completed"
        assert tracker._trace_lines[0]["overall_passed"] is True

    def test_save_trace(self):
        """测试保存轨迹到 JSONL 文件。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = os.path.join(tmpdir, "trace.jsonl")
            tracker = ProvenanceTracker(trace_path=trace_path)

            seed = _make_seed()
            tracker.record_seed(seed)
            tracker.record_generalization(seed, ["v1"], {"model": "test"})
            tracker.save_trace()

            assert os.path.exists(trace_path)
            with open(trace_path) as f:
                lines = f.readlines()
            assert len(lines) == 2

    def test_save_trace_no_path(self):
        """测试未设置轨迹路径时跳过保存。"""
        tracker = ProvenanceTracker(trace_path=None)
        seed = _make_seed()
        tracker.record_seed(seed)
        tracker.save_trace()  # 不应抛出异常

    def test_get_statistics_with_records(self):
        """测试有记录时的统计信息。"""
        tracker = ProvenanceTracker()
        seed = _make_seed()

        # 构建两条记录
        tracker.build_record(
            seed=seed,
            variant="帮我放首晴天",
            gen_metadata={"model": "test"},
            ver_result={
                "overall_passed": True,
                "confidence_score": 0.9,
                "rule_check": {"stage": "rule", "passed": True, "score": 1.0, "reason": "ok"},
                "semantic_check": {"stage": "semantic", "passed": True, "score": 0.9, "reason": "ok"},
                "safety_check": {"stage": "safety", "passed": True, "score": 0.95, "reason": "ok"},
            },
        )
        tracker.build_record(
            seed=seed,
            variant="播放视频",
            gen_metadata={"model": "test"},
            ver_result={
                "overall_passed": False,
                "confidence_score": 0.3,
                "rule_check": {"stage": "rule", "passed": False, "score": 0.0, "reason": "fail"},
            },
        )

        stats = tracker.get_statistics()
        assert stats["total_records"] == 2
        assert stats["total_passed"] == 1
        assert stats["total_rejected"] == 1
        assert stats["pass_rate"] == 0.5
        assert "音乐" in stats["by_domain"]

    def test_save_records(self):
        """测试保存记录到 JSON 文件。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "records.json")
            tracker = ProvenanceTracker()
            seed = _make_seed()

            tracker.build_record(
                seed=seed,
                variant="帮我放首晴天",
                gen_metadata={"model": "test"},
                ver_result={"overall_passed": True, "confidence_score": 0.9},
            )
            tracker.save(output_path)

            assert os.path.exists(output_path)
            with open(output_path) as f:
                data = json.load(f)
            assert len(data) == 1
            assert data[0]["variant"] == "帮我放首晴天"

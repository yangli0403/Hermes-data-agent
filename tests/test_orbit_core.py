"""
Car-ORBIT-Agent 核心模块单元测试。

覆盖：ConfigLoader、SeedEngine、RuleVerifier、ProvenanceTracker、
       CascadeOrchestrator、OrbitDatasetAdapter
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config_loader import ConfigLoader
from core.seed_engine import SeedEngine, Seed
from core.rule_verifier import RuleVerifier, StageResult
from core.provenance_tracker import ProvenanceTracker, OrbitRecord
from core.cascade_orchestrator import CascadeOrchestrator, VerificationResult
from scripts.orbit_dataset_adapter import OrbitDatasetAdapter


# =====================================================================
# ConfigLoader 测试
# =====================================================================

class TestConfigLoader:
    """ConfigLoader 单元测试。"""

    def test_default_config(self):
        """测试默认配置加载。"""
        loader = ConfigLoader()
        config = loader.load()
        assert "orbit" in config
        assert config["orbit"]["generalization"]["num_variants"] == 5

    def test_get_dot_path(self):
        """测试点分路径获取。"""
        loader = ConfigLoader()
        loader.load()
        model = loader.get("orbit.model.generation")
        assert model == "gpt-4.1-mini"

    def test_get_missing_key(self):
        """测试获取不存在的键。"""
        loader = ConfigLoader()
        loader.load()
        result = loader.get("orbit.nonexistent.key", "fallback")
        assert result == "fallback"

    def test_override(self):
        """测试配置覆盖。"""
        loader = ConfigLoader()
        loader.load()
        loader.override("orbit.model.generation", "gpt-4.1-nano")
        assert loader.get("orbit.model.generation") == "gpt-4.1-nano"

    def test_load_yaml_file(self):
        """测试从 YAML 文件加载配置。"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({"orbit": {"generalization": {"num_variants": 10}}}, f)
            f.flush()
            loader = ConfigLoader(config_path=f.name)
            assert loader.get("orbit.generalization.num_variants") == 10
            # 默认值应保留
            assert loader.get("orbit.model.generation") == "gpt-4.1-mini"
        os.unlink(f.name)

    def test_file_not_found(self):
        """测试文件不存在时抛出异常。"""
        with pytest.raises(FileNotFoundError):
            ConfigLoader(config_path="/nonexistent/path.yaml")


# =====================================================================
# SeedEngine 测试
# =====================================================================

class TestSeedEngine:
    """SeedEngine 单元测试。"""

    def _create_sample_config(self) -> str:
        """创建示例功能树配置文件。"""
        config = {
            "vehicle_tree": {
                "domains": [
                    {
                        "name": "空调",
                        "functions": [
                            {
                                "name": "温度调节",
                                "sub_functions": [
                                    {
                                        "name": "设置温度",
                                        "utterance_template": "把空调调到{temperature}度",
                                        "params": {
                                            "temperature": ["22", "24", "26"],
                                        },
                                    }
                                ],
                            },
                            {
                                "name": "开关",
                                "utterance_template": "打开空调",
                                "params": {},
                            },
                        ],
                    }
                ]
            }
        }
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
        yaml.dump(config, f, allow_unicode=True)
        f.flush()
        f.close()
        return f.name

    def test_generate_from_config(self):
        """测试从配置文件生成种子。"""
        config_path = self._create_sample_config()
        try:
            engine = SeedEngine()
            seeds = engine.generate_from_config(config_path)
            # 3 个温度参数组合 + 1 个无参数 = 4 个种子
            assert len(seeds) == 4
            assert all(isinstance(s, Seed) for s in seeds)
            # 检查参数替换
            temp_seeds = [s for s in seeds if s.params]
            assert len(temp_seeds) == 3
            assert "22" in temp_seeds[0].standard_utterance or "24" in temp_seeds[0].standard_utterance
        finally:
            os.unlink(config_path)

    def test_generate_with_limit(self):
        """测试种子数量限制。"""
        config_path = self._create_sample_config()
        try:
            engine = SeedEngine()
            seeds = engine.generate_from_config(config_path, max_seeds=2)
            assert len(seeds) == 2
        finally:
            os.unlink(config_path)

    def test_seed_to_dict_roundtrip(self):
        """测试 Seed 序列化和反序列化。"""
        seed = Seed(
            seed_id="test_001",
            domain="空调",
            function="温度调节",
            standard_utterance="把空调调到22度",
            params={"temperature": "22"},
        )
        d = seed.to_dict()
        restored = Seed.from_dict(d)
        assert restored.seed_id == seed.seed_id
        assert restored.domain == seed.domain
        assert restored.params == seed.params

    def test_file_not_found(self):
        """测试文件不存在时抛出异常。"""
        engine = SeedEngine()
        with pytest.raises(FileNotFoundError):
            engine.generate_from_config("/nonexistent/config.yaml")

    def test_empty_config(self):
        """测试空配置文件。"""
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
        yaml.dump({}, f)
        f.flush()
        f.close()
        try:
            engine = SeedEngine()
            with pytest.raises(ValueError):
                engine.generate_from_config(f.name)
        finally:
            os.unlink(f.name)


# =====================================================================
# RuleVerifier 测试
# =====================================================================

class TestRuleVerifier:
    """RuleVerifier 单元测试。"""

    def _make_seed(self, utterance="打开空调", params=None):
        return Seed(
            seed_id="test_001",
            domain="空调",
            function="开关",
            standard_utterance=utterance,
            params=params or {},
        )

    def test_valid_variant(self):
        """测试合法变体通过验证。"""
        verifier = RuleVerifier()
        seed = self._make_seed()
        result = verifier.verify("帮我开一下空调", seed)
        assert result.passed is True
        assert result.score == 1.0

    def test_empty_variant(self):
        """测试空变体被拒绝。"""
        verifier = RuleVerifier()
        seed = self._make_seed()
        result = verifier.verify("", seed)
        assert result.passed is False
        assert "为空" in result.reason

    def test_too_short(self):
        """测试过短变体被拒绝。"""
        verifier = RuleVerifier(min_length=3)
        seed = self._make_seed()
        result = verifier.verify("开", seed)
        assert result.passed is False
        assert "过短" in result.reason

    def test_too_long(self):
        """测试过长变体被拒绝。"""
        verifier = RuleVerifier(max_length=10)
        seed = self._make_seed()
        result = verifier.verify("请帮我把车里的空调打开好吗我觉得有点热了", seed)
        assert result.passed is False
        assert "过长" in result.reason

    def test_missing_params(self):
        """测试缺少关键参数被拒绝。"""
        verifier = RuleVerifier()
        seed = self._make_seed(
            utterance="把空调调到22度",
            params={"temperature": "22"},
        )
        result = verifier.verify("调一下空调温度", seed)
        assert result.passed is False
        assert "参数" in result.reason

    def test_params_present(self):
        """测试参数存在时通过。"""
        verifier = RuleVerifier()
        seed = self._make_seed(
            utterance="把空调调到22度",
            params={"temperature": "22"},
        )
        result = verifier.verify("空调温度设为22度", seed)
        assert result.passed is True

    def test_vehicle_constraint(self):
        """测试车辆约束规则（行驶中禁止视频）。"""
        verifier = RuleVerifier()
        seed = self._make_seed(utterance="播放视频")
        result = verifier.verify("帮我播放视频", seed)
        assert result.passed is False
        assert "约束" in result.reason

    def test_batch_verify(self):
        """测试批量验证。"""
        verifier = RuleVerifier()
        seed = self._make_seed()
        results = verifier.verify_batch(["开空调", "帮我开空调", ""], seed)
        assert len(results) == 3
        assert results[0].passed is True
        assert results[1].passed is True
        assert results[2].passed is False


# =====================================================================
# ProvenanceTracker 测试
# =====================================================================

class TestProvenanceTracker:
    """ProvenanceTracker 单元测试。"""

    def test_build_record(self):
        """测试构建最终记录。"""
        tracker = ProvenanceTracker()
        seed = Seed(
            seed_id="test_001",
            domain="空调",
            function="温度调节",
            standard_utterance="把空调调到22度",
        )
        record = tracker.build_record(
            seed=seed,
            variant="帮我把空调调到22度",
            gen_metadata={"model": "gpt-4.1-mini", "dimensions": ["colloquial"]},
            ver_result={
                "overall_passed": True,
                "confidence_score": 0.9,
                "rule_check": {"stage": "rule", "passed": True, "score": 1.0, "reason": "ok"},
                "semantic_check": {"stage": "semantic", "passed": True, "score": 0.85, "reason": "ok"},
                "safety_check": {"stage": "safety", "passed": True, "score": 0.95, "reason": "ok"},
            },
        )
        assert isinstance(record, OrbitRecord)
        assert record.standard_utterance == "把空调调到22度"
        assert record.variant == "帮我把空调调到22度"
        assert record.label_quality == "synthetic_verified"
        assert len(record.verification_chain) == 3

    def test_statistics_empty(self):
        """测试空记录的统计。"""
        tracker = ProvenanceTracker()
        stats = tracker.get_statistics()
        assert stats["total_records"] == 0
        assert stats["pass_rate"] == 0.0

    def test_save_and_load(self):
        """测试保存记录到 JSON。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = ProvenanceTracker()
            seed = Seed(seed_id="t1", domain="空调", function="开关", standard_utterance="开空调")
            tracker.build_record(
                seed=seed, variant="开空调",
                gen_metadata={},
                ver_result={"overall_passed": True, "confidence_score": 0.9},
            )
            output_path = os.path.join(tmpdir, "records.json")
            tracker.save(output_path)

            with open(output_path, "r") as f:
                data = json.load(f)
            assert len(data) == 1
            assert data[0]["standard_utterance"] == "开空调"


# =====================================================================
# CascadeOrchestrator 测试（使用 Mock）
# =====================================================================

class TestCascadeOrchestrator:
    """CascadeOrchestrator 单元测试。"""

    def _make_seed(self):
        return Seed(
            seed_id="test_001",
            domain="空调",
            function="开关",
            standard_utterance="打开空调",
        )

    def test_rule_failure_short_circuits(self):
        """测试规则验证失败时短路。"""
        mock_rule = MagicMock()
        mock_rule.verify.return_value = StageResult(
            stage="rule", passed=False, score=0.0, reason="过短"
        )
        mock_semantic = MagicMock()
        mock_safety = MagicMock()

        orchestrator = CascadeOrchestrator(
            rule_verifier=mock_rule,
            semantic_verifier=mock_semantic,
            safety_verifier=mock_safety,
        )

        result = orchestrator.verify("x", self._make_seed())
        assert result.overall_passed is False
        assert result.semantic_check is None
        assert result.safety_check is None
        # 语义和安全验证不应被调用
        mock_semantic.verify.assert_not_called()
        mock_safety.verify.assert_not_called()

    def test_semantic_failure_short_circuits(self):
        """测试语义验证失败时短路。"""
        mock_rule = MagicMock()
        mock_rule.verify.return_value = StageResult(
            stage="rule", passed=True, score=1.0, reason="ok"
        )
        mock_semantic = MagicMock()
        mock_semantic.verify.return_value = StageResult(
            stage="semantic", passed=False, score=0.3, reason="语义不一致"
        )
        mock_safety = MagicMock()

        orchestrator = CascadeOrchestrator(
            rule_verifier=mock_rule,
            semantic_verifier=mock_semantic,
            safety_verifier=mock_safety,
        )

        result = orchestrator.verify("开窗户", self._make_seed())
        assert result.overall_passed is False
        assert result.semantic_check is not None
        assert result.safety_check is None
        mock_safety.verify.assert_not_called()

    def test_all_pass(self):
        """测试全部通过。"""
        mock_rule = MagicMock()
        mock_rule.verify.return_value = StageResult(
            stage="rule", passed=True, score=1.0, reason="ok"
        )
        mock_semantic = MagicMock()
        mock_semantic.verify.return_value = StageResult(
            stage="semantic", passed=True, score=0.9, reason="ok"
        )
        mock_safety = MagicMock()
        mock_safety.verify.return_value = StageResult(
            stage="safety", passed=True, score=0.95, reason="ok"
        )

        orchestrator = CascadeOrchestrator(
            rule_verifier=mock_rule,
            semantic_verifier=mock_semantic,
            safety_verifier=mock_safety,
        )

        result = orchestrator.verify("帮我开一下空调", self._make_seed())
        assert result.overall_passed is True
        assert result.confidence_score > 0.8


# =====================================================================
# OrbitDatasetAdapter 测试
# =====================================================================

class TestOrbitDatasetAdapter:
    """OrbitDatasetAdapter 单元测试。"""

    def _make_records(self) -> list:
        return [
            OrbitRecord(
                record_id="r1",
                standard_utterance="打开空调",
                variant="开空调",
                source_chain={"domain": "空调", "function": "开关"},
                verification_chain=[
                    {"stage": "rule", "passed": True, "score": 1.0, "reason": "ok"},
                    {"stage": "semantic", "passed": True, "score": 0.9, "reason": "ok"},
                    {"stage": "safety", "passed": True, "score": 0.95, "reason": "ok"},
                ],
                confidence_score=0.93,
                label_quality="synthetic_verified",
            ),
            OrbitRecord(
                record_id="r2",
                standard_utterance="打开空调",
                variant="空调开",
                source_chain={"domain": "空调", "function": "开关"},
                verification_chain=[
                    {"stage": "rule", "passed": True, "score": 1.0, "reason": "ok"},
                    {"stage": "semantic", "passed": False, "score": 0.4, "reason": "不自然"},
                ],
                confidence_score=0.36,
                label_quality="synthetic_rejected",
            ),
        ]

    def test_to_json(self):
        """测试 JSON 导出。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            adapter = OrbitDatasetAdapter()
            path = adapter.to_json(self._make_records(), os.path.join(tmpdir, "out.json"))
            with open(path, "r") as f:
                data = json.load(f)
            assert len(data) == 2

    def test_to_jsonl(self):
        """测试 JSONL 导出。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            adapter = OrbitDatasetAdapter()
            path = adapter.to_jsonl(self._make_records(), os.path.join(tmpdir, "out.jsonl"))
            with open(path, "r") as f:
                lines = f.readlines()
            assert len(lines) == 2

    def test_to_excel(self):
        """测试 Excel 导出。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            adapter = OrbitDatasetAdapter()
            path = adapter.to_excel(self._make_records(), os.path.join(tmpdir, "out.xlsx"))
            assert os.path.exists(path)

    def test_generate_summary(self):
        """测试统计摘要生成。"""
        adapter = OrbitDatasetAdapter()
        summary = adapter.generate_summary(self._make_records())
        assert summary["total_records"] == 2
        assert summary["total_passed"] == 1
        assert summary["total_rejected"] == 1
        assert summary["pass_rate"] == 0.5
        assert "空调" in summary["by_domain"]

    def test_empty_summary(self):
        """测试空记录的统计摘要。"""
        adapter = OrbitDatasetAdapter()
        summary = adapter.generate_summary([])
        assert summary["total_records"] == 0
        assert summary["pass_rate"] == 0.0

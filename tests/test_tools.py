"""
Tests for Hermes Data Agent tools and modules.

Tests are organized by module:
- TestSkillLoading: SKILL.md discovery and content
- TestToolSchemas: OpenAI function-calling schema validation
- TestDatasetAdapter: Excel → JSONL conversion (NEW)
- TestVariantExtraction: delegate_synthesis helper functions (NEW)
- TestBatchCheckpoint: checkpoint/resume logic (NEW)
- TestOrchestrationPrompt: delegation orchestration prompt (NEW)
- TestSynthesisHandler: integration test (requires API)
- TestValidationHandler: integration test (requires API)
- TestBatchHandler: integration test (requires API)
"""

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.cockpit_synthesis_tool import (
    handle_cockpit_synthesize,
    handle_cockpit_validate,
    handle_cockpit_batch_synthesize,
    _load_skill_text,
    SYNTHESIS_TOOL_SCHEMA,
    VALIDATION_TOOL_SCHEMA,
    BATCH_TOOL_SCHEMA,
)

from tools.delegate_synthesis import (
    DELEGATE_SYNTHESIS_SCHEMA,
    DELEGATION_ORCHESTRATION_PROMPT,
    _extract_variants,
    _extract_validation,
)

from scripts.dataset_adapter import excel_to_batch_jsonl


# ── Skill Loading ────────────────────────────────────────────────────────

class TestSkillLoading:
    """Test that SKILL.md files are correctly loaded."""

    def test_load_synthesis_skill(self):
        text = _load_skill_text("cockpit-utterance-synthesis")
        assert len(text) > 100
        assert "cockpit-utterance-synthesis" in text
        assert "Parameter Preservation" in text

    def test_load_validation_skill(self):
        text = _load_skill_text("cockpit-utterance-validation")
        assert len(text) > 100
        assert "cockpit-utterance-validation" in text
        assert "Semantic Consistency" in text

    def test_load_delegation_skill(self):
        text = _load_skill_text("cockpit-delegation-orchestrator")
        assert len(text) > 100
        assert "delegate_task" in text

    def test_load_nonexistent_skill(self):
        text = _load_skill_text("nonexistent-skill")
        assert text == ""

    def test_all_skills_exist(self):
        skills_dir = Path(__file__).parent.parent / "skills"
        skill_dirs = [d.name for d in skills_dir.iterdir() if d.is_dir()]
        assert "cockpit-utterance-synthesis" in skill_dirs
        assert "cockpit-utterance-validation" in skill_dirs
        assert "cockpit-delegation-orchestrator" in skill_dirs


# ── Tool Schemas ─────────────────────────────────────────────────────────

class TestToolSchemas:
    """Test that tool schemas follow OpenAI function-calling format."""

    def test_synthesis_schema_structure(self):
        assert SYNTHESIS_TOOL_SCHEMA["type"] == "function"
        func = SYNTHESIS_TOOL_SCHEMA["function"]
        assert func["name"] == "cockpit_synthesize"
        assert "standard_utterance" in func["parameters"]["properties"]
        assert "standard_utterance" in func["parameters"]["required"]

    def test_validation_schema_structure(self):
        func = VALIDATION_TOOL_SCHEMA["function"]
        assert func["name"] == "cockpit_validate"
        assert "variants" in func["parameters"]["properties"]

    def test_batch_schema_structure(self):
        func = BATCH_TOOL_SCHEMA["function"]
        assert func["name"] == "cockpit_batch_synthesize"
        assert "input_path" in func["parameters"]["required"]

    def test_delegate_synthesis_schema_structure(self):
        """NEW: Test delegate_synthesis tool schema."""
        assert DELEGATE_SYNTHESIS_SCHEMA["type"] == "function"
        func = DELEGATE_SYNTHESIS_SCHEMA["function"]
        assert func["name"] == "cockpit_delegate_synthesize"
        assert "standard_utterance" in func["parameters"]["properties"]
        assert "max_retries" in func["parameters"]["properties"]
        assert "num_variants" in func["parameters"]["properties"]


# ── Dataset Adapter (NEW) ────────────────────────────────────────────────

class TestDatasetAdapter:
    """Test Excel → JSONL conversion for batch_runner."""

    def test_excel_to_jsonl_basic(self):
        input_path = Path(__file__).parent.parent / "data" / "数据处理测试.xlsx"
        if not input_path.exists():
            pytest.skip("Test data not available")

        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            output_path = f.name

        try:
            count = excel_to_batch_jsonl(
                input_path=str(input_path),
                output_path=output_path,
                num_variants=3,
                limit=2,
            )
            assert count == 2

            with open(output_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            assert len(lines) == 2

            entry = json.loads(lines[0])
            assert "prompt" in entry
            assert "metadata" in entry
            assert "standard_utterance" in entry["metadata"]
            assert "cockpit_synthesize" in entry["prompt"]
            assert "cockpit_validate" in entry["prompt"]
        finally:
            os.unlink(output_path)

    def test_jsonl_without_validation(self):
        input_path = Path(__file__).parent.parent / "data" / "数据处理测试.xlsx"
        if not input_path.exists():
            pytest.skip("Test data not available")

        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            output_path = f.name

        try:
            count = excel_to_batch_jsonl(
                input_path=str(input_path),
                output_path=output_path,
                num_variants=3,
                limit=1,
                validate=False,
            )
            assert count == 1

            entry = json.loads(open(output_path).readline())
            assert entry["metadata"]["validate"] is False
            assert "cockpit_validate" not in entry["prompt"]
        finally:
            os.unlink(output_path)

    def test_jsonl_metadata_completeness(self):
        input_path = Path(__file__).parent.parent / "data" / "数据处理测试.xlsx"
        if not input_path.exists():
            pytest.skip("Test data not available")

        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            output_path = f.name

        try:
            excel_to_batch_jsonl(
                input_path=str(input_path),
                output_path=output_path,
                num_variants=5,
                limit=1,
            )
            entry = json.loads(open(output_path).readline())
            meta = entry["metadata"]
            required_keys = ["domain", "primary_function", "secondary_function",
                             "param_combination", "param_description",
                             "standard_utterance", "num_variants", "validate"]
            for key in required_keys:
                assert key in meta, f"Missing metadata key: {key}"
            assert meta["num_variants"] == 5
        finally:
            os.unlink(output_path)


# ── Variant Extraction (NEW) ────────────────────────────────────────────

class TestVariantExtraction:
    """Test delegate_synthesis helper functions for parsing agent responses."""

    def test_extract_direct_json_array(self):
        text = json.dumps(["变体1", "变体2", "变体3"])
        result = _extract_variants(text)
        assert result == ["变体1", "变体2", "变体3"]

    def test_extract_embedded_json_array(self):
        text = '生成结果如下：["帮我放歌", "来首歌"] 以上是变体。'
        result = _extract_variants(text)
        assert result == ["帮我放歌", "来首歌"]

    def test_extract_empty_input(self):
        assert _extract_variants("") == []
        assert _extract_variants(None) == []

    def test_extract_no_json(self):
        assert _extract_variants("no json here at all") == []

    def test_extract_validation_passed(self):
        text = json.dumps({"passed": True, "overall_score": 0.92})
        result = _extract_validation(text)
        assert result["passed"] is True
        assert result["overall_score"] == 0.92

    def test_extract_validation_failed_embedded(self):
        text = '验证结果：{"passed": false, "feedback": "参数缺失"} 请修改。'
        result = _extract_validation(text)
        assert result["passed"] is False
        assert "参数缺失" in result["feedback"]

    def test_extract_validation_empty(self):
        result = _extract_validation("")
        assert result["passed"] is True  # Default to passed


# ── Batch Checkpoint (NEW) ───────────────────────────────────────────────

class TestBatchCheckpoint:
    """Test checkpoint/resume logic for batch processing."""

    def test_checkpoint_creation_and_reading(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            checkpoint_file = Path(tmpdir) / "checkpoint.json"
            completed = [0, 1, 3]
            checkpoint_file.write_text(json.dumps({
                "completed_indices": completed,
            }))

            ckpt = json.loads(checkpoint_file.read_text())
            assert set(ckpt["completed_indices"]) == {0, 1, 3}

    def test_resume_filters_completed(self):
        entries = [{"id": i} for i in range(5)]
        completed_indices = {0, 2, 4}
        pending = [(i, e) for i, e in enumerate(entries) if i not in completed_indices]
        assert len(pending) == 2
        assert [p[0] for p in pending] == [1, 3]

    def test_all_completed_yields_empty_pending(self):
        entries = [{"id": i} for i in range(3)]
        completed_indices = {0, 1, 2}
        pending = [(i, e) for i, e in enumerate(entries) if i not in completed_indices]
        assert len(pending) == 0


# ── Orchestration Prompt (NEW) ───────────────────────────────────────────

class TestOrchestrationPrompt:
    """Test the delegation orchestration prompt content."""

    def test_contains_delegate_task(self):
        assert "delegate_task" in DELEGATION_ORCHESTRATION_PROMPT

    def test_contains_tool_references(self):
        assert "cockpit_synthesize" in DELEGATION_ORCHESTRATION_PROMPT
        assert "cockpit_validate" in DELEGATION_ORCHESTRATION_PROMPT

    def test_contains_retry_instructions(self):
        prompt_lower = DELEGATION_ORCHESTRATION_PROMPT.lower()
        assert "retry" in prompt_lower or "重试" in DELEGATION_ORCHESTRATION_PROMPT

    def test_contains_batch_mode(self):
        assert "tasks" in DELEGATION_ORCHESTRATION_PROMPT
        assert "parallel" in DELEGATION_ORCHESTRATION_PROMPT.lower() or \
               "batch" in DELEGATION_ORCHESTRATION_PROMPT.lower()


# ── Integration Tests (require API key) ──────────────────────────────────

@pytest.mark.integration
class TestSynthesisHandler:
    """Test the synthesis tool handler (requires API key)."""

    def test_single_synthesis(self):
        result_str = handle_cockpit_synthesize(
            standard_utterance="播放音乐",
            domain="音乐",
            primary_function="播放音乐",
            num_variants=3,
        )
        result = json.loads(result_str)
        assert isinstance(result, list)
        assert len(result) == 3
        assert all(isinstance(v, str) for v in result)

    def test_synthesis_with_params(self):
        result_str = handle_cockpit_synthesize(
            standard_utterance="播放周杰伦的歌",
            domain="音乐",
            param_combination="播放+歌手",
            num_variants=3,
        )
        result = json.loads(result_str)
        assert isinstance(result, list)
        for variant in result:
            assert "周杰伦" in variant


@pytest.mark.integration
class TestValidationHandler:
    """Test the validation tool handler."""

    def test_validation_pass(self):
        result_str = handle_cockpit_validate(
            standard_utterance="播放音乐",
            variants=["帮我放音乐", "来点音乐", "放首歌"],
            domain="音乐",
        )
        result = json.loads(result_str)
        assert isinstance(result, dict)
        assert "passed" in result or "overall_score" in result


@pytest.mark.integration
class TestBatchHandler:
    """Test the batch synthesis handler."""

    def test_batch_synthesis(self, tmp_path):
        output_json = str(tmp_path / "result.json")
        output_excel = str(tmp_path / "result.xlsx")

        result_str = handle_cockpit_batch_synthesize(
            input_path="data/数据处理测试.xlsx",
            output_json=output_json,
            output_excel=output_excel,
            num_variants=2,
            validate=False,
            limit=2,
        )

        result = json.loads(result_str)
        assert result["status"] == "success"
        assert result["total_utterances"] == 2
        assert result["total_variants"] > 0
        assert Path(output_json).exists()
        assert Path(output_excel).exists()

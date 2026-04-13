"""
Tests for cockpit synthesis tools.

Tests the tool handlers in standalone mode (without hermes-agent).
"""

import json
import sys
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

    def test_load_nonexistent_skill(self):
        text = _load_skill_text("nonexistent-skill")
        assert text == ""


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


class TestSynthesisHandler:
    """Test the synthesis tool handler (requires API key)."""

    @pytest.mark.integration
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

    @pytest.mark.integration
    def test_synthesis_with_params(self):
        result_str = handle_cockpit_synthesize(
            standard_utterance="播放周杰伦的歌",
            domain="音乐",
            param_combination="播放+歌手",
            num_variants=3,
        )
        result = json.loads(result_str)
        assert isinstance(result, list)
        # Check parameter retention
        for variant in result:
            assert "周杰伦" in variant


class TestValidationHandler:
    """Test the validation tool handler."""

    @pytest.mark.integration
    def test_validation_pass(self):
        result_str = handle_cockpit_validate(
            standard_utterance="播放音乐",
            variants=["帮我放音乐", "来点音乐", "放首歌"],
            domain="音乐",
        )
        result = json.loads(result_str)
        assert isinstance(result, dict)
        assert "passed" in result or "overall_score" in result


class TestBatchHandler:
    """Test the batch synthesis handler."""

    @pytest.mark.integration
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

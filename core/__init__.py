"""
Hermes Data Agent 核心引擎层。

本包包含 ORBIT 流水线和 VLM 视觉链路的所有核心业务逻辑，
独立于 Hermes 工具层和 CLI 层。
"""

# ── ORBIT 文本链路 ──────────────────────────────────────────────────
from core.seed_engine import SeedEngine, Seed
from core.generalization_engine import GeneralizationEngine, GeneralizationResult
from core.rule_verifier import RuleVerifier, StageResult
from core.semantic_verifier import SemanticVerifier
from core.safety_verifier import SafetyVerifier
from core.cascade_orchestrator import CascadeOrchestrator, VerificationResult
from core.llm_client import LLMClient
from core.provenance_tracker import ProvenanceTracker, OrbitRecord
from core.config_loader import ConfigLoader

# ── VLM 视觉链路（新增） ──────────────────────────────────────────
from core.contracts import (
    BaseRecord,
    VisualSeed,
    VLMSample,
    VLMRecord,
    LabelQuality,
    QuestionType,
)
from core.image_client import ImageClient, ImageResult
from core.vlm_client import VLMClient, VLMJudgment
from core.client_factory import ClientFactory
from core.visual_seed_engine import VisualSeedEngine
from core.visual_generalization_engine import VisualGeneralizationEngine
from core.image_synthesis_coordinator import ImageSynthesisCoordinator
from core.schema_verifier import SchemaVerifier
from core.consistency_verifier import ConsistencyVerifier
from core.vision_consistency_verifier import VisionConsistencyVerifier
from core.vlm_pipeline_runner import VLMPipelineRunner, PipelineResult, BatchPipelineResult

__all__ = [
    # ORBIT 文本链路
    "SeedEngine",
    "Seed",
    "GeneralizationEngine",
    "GeneralizationResult",
    "RuleVerifier",
    "StageResult",
    "SemanticVerifier",
    "SafetyVerifier",
    "CascadeOrchestrator",
    "VerificationResult",
    "LLMClient",
    "ProvenanceTracker",
    "OrbitRecord",
    "ConfigLoader",
    # VLM 视觉链路
    "BaseRecord",
    "VisualSeed",
    "VLMSample",
    "VLMRecord",
    "LabelQuality",
    "QuestionType",
    "ImageClient",
    "ImageResult",
    "VLMClient",
    "VLMJudgment",
    "ClientFactory",
    "VisualSeedEngine",
    "VisualGeneralizationEngine",
    "ImageSynthesisCoordinator",
    "SchemaVerifier",
    "ConsistencyVerifier",
    "VisionConsistencyVerifier",
    "VLMPipelineRunner",
    "PipelineResult",
    "BatchPipelineResult",
]

# CLAUDE.md — AI 架构指南

本文档为 AI 编码助手（Claude、Cursor、Copilot 等）提供项目上下文和开发规范，以便在后续开发中保持代码一致性。

## 项目概述

Hermes-data-agent 是一个 Agent 化的数据合成平台，支持多种 NLU/VLM 训练数据的自动化生成。项目包含两条独立的数据合成链路：

- **ORBIT 文本链路 (v0.2.0)**：借鉴 ORBIT 框架方法论，为车载座舱语音助手生成高质量话术变体数据
- **VLM 视觉链路 (v0.3.0)**：生成视觉问答（VQA）训练数据，包含图像生成、视觉理解和三层验证

## 目录结构

```
Hermes-data-agent/
├── core/                              # 核心引擎层（双轨共用）
│   ├── __init__.py                    # 公共接口导出（ORBIT + VLM）
│   ├── config_loader.py               # 配置加载器（含 vlm 命名空间）
│   ├── contracts.py                   # VLM 数据契约（VisualSeed、VLMSample、VLMRecord）
│   │
│   │   # ── ORBIT 文本链路模块 ──
│   ├── llm_client.py                  # LLM 客户端（重试、JSON 解析）
│   ├── seed_engine.py                 # 种子生成引擎
│   ├── generalization_engine.py       # 多维度泛化引擎
│   ├── rule_verifier.py               # 规则验证器（纯 Python）
│   ├── semantic_verifier.py           # 语义验证器（LLM）
│   ├── safety_verifier.py             # 安全验证器（LLM）
│   ├── cascade_orchestrator.py        # 级联验证编排器
│   ├── provenance_tracker.py          # 来源链/验证链追踪器
│   │
│   │   # ── VLM 视觉链路模块 ──
│   ├── image_client.py                # 图像生成客户端（DALL-E 等）
│   ├── vlm_client.py                  # 视觉语言模型客户端（判定/描述）
│   ├── client_factory.py              # 统一客户端工厂
│   ├── visual_seed_engine.py          # 视觉任务种子引擎
│   ├── visual_generalization_engine.py # 视觉泛化引擎
│   ├── image_synthesis_coordinator.py # 图像合成协调器
│   ├── schema_verifier.py             # 结构校验器（零 API 成本）
│   ├── consistency_verifier.py        # 文本自洽校验器（LLM）
│   ├── vision_consistency_verifier.py # 图像内容一致性校验器（VLM）
│   └── vlm_pipeline_runner.py         # VLM 管线编排器
│
├── tools/                             # Hermes 工具层（ORBIT 专用）
│   ├── orbit_seed_tool.py
│   ├── orbit_generalize_tool.py
│   ├── orbit_verify_tool.py
│   └── orbit_toolset_adapter.py
│
├── scripts/                           # CLI 和批处理脚本
│   ├── cli.py                         # 主 CLI 入口（orbit + vlm 子命令）
│   ├── orbit_dataset_adapter.py       # ORBIT 输出格式转换
│   ├── vlm_dataset_adapter.py         # VLM 双轨导出适配器
│   ├── batch_synthesize.py            # 现有：批量合成
│   └── dataset_adapter.py             # 现有：数据集适配
│
├── configs/                           # 配置文件
│   ├── default.yaml                   # 全局默认配置（含 vlm 命名空间）
│   ├── orbit_vehicle_tree_sample.yaml # ORBIT 示例功能树
│   └── vlm_task_sample.yaml           # VLM 任务配置示例
│
├── tests/                             # 测试（217 个，core/ 覆盖率 96%）
│   ├── test_orbit_core.py             # ORBIT 纯逻辑单元测试（30 个）
│   ├── test_orbit_llm_mock.py         # ORBIT LLM Mock 测试（46 个）
│   ├── test_tools.py                  # ORBIT 工具测试（30 个）
│   ├── test_vlm_core.py              # VLM 纯逻辑单元测试（44 个）
│   ├── test_vlm_llm_mock.py          # VLM LLM/VLM Mock 测试（36 个）
│   └── test_vlm_coverage_boost.py    # VLM 覆盖率补充测试（31 个）
│
├── skills/                            # Hermes 技能定义
│   └── car-orbit-synthesis/SKILL.md
│
├── diagrams/                          # 架构图
│   ├── architecture.mmd
│   └── architecture.png
│
└── docs/                              # 补充文档
```

## 架构原则

### 分层架构

项目采用六层分层架构，**严格遵循单向依赖**：

```
CLI 入口层 → 技能层 → 工具层 → 核心引擎层 → 基础设施层 → 适配器层
```

- `scripts/cli.py` 可以导入 `core/` 和 `tools/`
- `tools/` 可以导入 `core/`
- `core/` 模块之间可以相互导入，但不得导入 `tools/` 或 `scripts/`
- 禁止循环依赖

### 核心设计模式

| 模式 | 适用链路 | 说明 |
|------|---------|------|
| 短路策略 | 双轨 | 验证失败时跳过后续层，节省 API 成本 |
| 延迟初始化 | 双轨 | 客户端延迟创建 OpenAI 实例，避免导入副作用 |
| 可选依赖 | 双轨 | hermes-agent 是可选依赖，核心功能不依赖它 |
| 数据驱动 | 双轨 | 泛化维度和验证规则通过配置定义 |
| 三层验证 | VLM | 结构校验(0 API) → 文本自洽(LLM) → 视觉一致(VLM) |
| 客户端工厂 | VLM | ClientFactory 统一创建 LLM/Image/VLM 客户端 |

## 编码规范

### Python 风格

- Python 3.11，使用 `from __future__ import annotations` 支持延迟类型注解
- 使用 `@dataclass` 定义数据结构
- 使用 `typing` 模块的类型注解（`List`、`Dict`、`Optional` 等）
- 使用 `logging` 模块记录日志，不使用 `print`
- 私有方法以 `_` 前缀命名
- 每个模块顶部有完整的 docstring 说明职责和公共接口

### 命名约定

| 类别 | 格式 | 示例 |
|------|------|------|
| 模块文件 | snake_case.py | visual_seed_engine.py |
| 类名 | PascalCase | VLMPipelineRunner |
| 方法和变量 | snake_case | generate_from_task |
| 常量 | UPPER_SNAKE_CASE | MAX_QUESTION_LENGTH |
| ORBIT 种子 ID | orbit_{领域}_{功能}_{编号} | orbit_nav_set_dest_001 |
| ORBIT 记录 ID | orbit_{seed_id}_{uuid[:6]} | orbit_nav_set_dest_001_a1b2c3 |
| VLM 种子 ID | vseed_{uuid[:8]} | vseed_1a2b3c4d |
| VLM 样本 ID | vsample_{uuid[:8]} | vsample_5e6f7g8h |
| VLM 记录 ID | vlm_{uuid[:12]} | vlm_a1b2c3d4e5f6 |

### 错误处理

| 场景 | 处理方式 |
|------|---------|
| LLM/VLM 调用失败 | 重试 3 次（指数退避），最终抛出 RuntimeError |
| 配置文件缺失 | 抛出 FileNotFoundError |
| 配置格式错误 | 抛出 ValueError 并附带明确描述 |
| 验证器 LLM 失败 | 返回保守评分（passed=False, score=0.5） |
| 图像文件不存在 | 抛出 FileNotFoundError |
| 图像生成失败 | 标记样本 status="failed"，继续处理下一个 |

### 测试规范

| 测试类型 | 文件命名 | 说明 |
|---------|---------|------|
| ORBIT 纯逻辑 | test_orbit_core.py | 不依赖外部服务 |
| ORBIT Mock | test_orbit_llm_mock.py | Mock LLM 调用 |
| VLM 纯逻辑 | test_vlm_core.py | 不依赖外部服务 |
| VLM Mock | test_vlm_llm_mock.py | Mock LLM/VLM/Image 调用 |
| VLM 边界 | test_vlm_coverage_boost.py | 覆盖率补充 |

- 测试类以 `Test` 前缀命名，测试方法以 `test_` 前缀命名
- 每个测试方法有中文 docstring 说明测试目的
- 使用 `_make_seed()` / `_make_vlm_sample()` 辅助函数创建测试数据

## 关键数据流

### ORBIT 文本链路

```
功能树 YAML → SeedEngine → [Seed] → GeneralizationEngine → [变体]
    → CascadeOrchestrator → [VerificationResult]
    → ProvenanceTracker → [OrbitRecord]
    → OrbitDatasetAdapter → JSON/JSONL/Excel
```

### VLM 视觉链路

```
任务配置 YAML → VisualSeedEngine → [VisualSeed]
    → VisualGeneralizationEngine → [VLMSample]
    → ImageSynthesisCoordinator → [VLMSample + 图像]
    → SchemaVerifier → ConsistencyVerifier → VisionConsistencyVerifier
    → VLMRecord.from_sample()
    → VLMDatasetAdapter → 训练 JSONL / 审阅 Excel
```

### VLM 三层验证管线

```
VLMSample → SchemaVerifier (纯 Python, 零成本)
    ├─ 失败 → 短路返回
    └─ 通过 → ConsistencyVerifier (LLM)
        ├─ 失败 → 短路返回
        └─ 通过 → VisionConsistencyVerifier (VLM)
            ├─ 失败 → 返回
            └─ 通过 → 计算综合置信度
```

## 核心数据模型

### ORBIT 链路

| 数据类 | 文件 | 说明 |
|--------|------|------|
| Seed | core/seed_engine.py | 种子（功能+参数+标准话术） |
| StageResult | core/rule_verifier.py | 单层验证结果 |
| VerificationResult | core/cascade_orchestrator.py | 级联验证结果 |
| OrbitRecord | core/provenance_tracker.py | 最终输出记录 |

### VLM 链路

| 数据类 | 文件 | 说明 |
|--------|------|------|
| VisualSeed | core/contracts.py | 视觉任务种子 |
| VLMSample | core/contracts.py | 中间态候选样本 |
| VLMRecord | core/contracts.py | 最终输出记录 |
| VLMJudgment | core/vlm_client.py | VLM 判定结果 |
| ImageResult | core/image_client.py | 图像生成结果 |

### 枚举类型

| 枚举 | 文件 | 值 |
|------|------|-----|
| LabelQuality | core/contracts.py | pending, verified, rejected, needs_review |
| QuestionType | core/contracts.py | descriptive, counting, spatial, comparative, reasoning, yes_no, identification |

## 添加新功能的指南

### 添加新的 VLM 验证层

1. 创建新的验证器文件 `core/xxx_verifier.py`
2. 实现 `verify(sample: VLMSample) -> StageResult` 接口
3. 在 `VLMPipelineRunner._run_verification()` 中注册新验证器
4. 在 `tests/test_vlm_llm_mock.py` 中添加 Mock 测试

### 添加新的 ORBIT 泛化维度

1. 在 `core/generalization_engine.py` 的 `DIMENSION_PROMPTS` 字典中添加新维度
2. 无需修改引擎代码，维度配置是数据驱动的

### 添加新的图像生成 Provider

1. 在 `core/image_client.py` 中扩展 `_call_api_with_retry()` 方法
2. 在 `core/client_factory.py` 中添加 Provider 映射
3. 在 `configs/vlm_task_sample.yaml` 中添加配置示例

### 添加新的 Hermes 工具

1. 在 `tools/` 中创建新的工具文件
2. 实现 `handle_xxx(params) -> Dict` 函数
3. 在文件底部使用 `ToolRegistry.register()` 注册
4. 在对应的 `toolset_adapter.py` 的工具列表中添加

## 常用命令

```bash
# ── ORBIT 链路 ──
python3 scripts/cli.py orbit --config configs/orbit_vehicle_tree_sample.yaml --output-dir output/orbit/
python3 scripts/cli.py orbit --config configs/orbit_vehicle_tree_sample.yaml --limit 5 --variants 3
python3 scripts/cli.py orbit --config configs/orbit_vehicle_tree_sample.yaml --skip-verify

# ── VLM 链路 ──
python3 scripts/cli.py vlm --config configs/vlm_task_sample.yaml --output-dir output/vlm/
python3 scripts/cli.py vlm --config configs/vlm_task_sample.yaml --limit 5
python3 scripts/cli.py vlm --config configs/vlm_task_sample.yaml --skip-image

# ── 测试 ──
python3 -m pytest tests/ -v                                          # 全部 217 个测试
python3 -m pytest tests/test_vlm_*.py -v                             # 仅 VLM（111 个）
python3 -m pytest tests/test_orbit_*.py -v                           # 仅 ORBIT（76 个）
python3 -m pytest tests/ --cov=core --cov-report=term-missing        # 覆盖率报告

# ── 项目信息 ──
python3 scripts/cli.py info
```

## 重要文档

| 文档 | 说明 |
|------|------|
| ARCHITECTURE.md | 双轨架构设计（六层架构、VLM 数据流、设计决策） |
| INTERFACE_DESIGN.md | 接口设计（ORBIT + VLM 全部公共 API 签名） |
| TESTING.md | 全量测试文档（217 个测试、96% core/ 覆盖率） |
| REQUIREMENTS_REFLECTION.md | 需求反思（ORBIT 97% + VLM 86% 覆盖率） |
| PRODUCT_SPEC.md | 产品规格说明 |
| configs/vlm_task_sample.yaml | VLM 任务配置示例 |
| skills/car-orbit-synthesis/SKILL.md | ORBIT Hermes 技能定义 |

## 已知待办

| 优先级 | 待办项 | 说明 |
|--------|--------|------|
| P1 | tools/vlm_* 工具层 | VLM 链路的 Hermes 工具封装尚未实现 |
| P1 | skills/vlm-data-synthesis/SKILL.md | VLM 技能定义文件尚未创建 |
| P2 | seed_engine.py Excel 路径测试 | 需要真实 .xlsx 文件的集成测试 |
| P2 | 真实 API 端到端测试 | 需要有效 API Key 的集成测试 |

# CLAUDE.md — AI 架构指南

本文档为 AI 编码助手（Claude、Cursor、Copilot 等）提供项目上下文和开发规范，以便在后续开发中保持代码一致性。

## 项目概述

Hermes-data-agent 是一个 Agent 化的数据合成平台，支持多种 NLU 训练数据的自动化生成。其中 **car-orbit-agent** 是核心模块之一，借鉴 ORBIT 框架的方法论，为车载座舱语音助手生成高质量话术变体数据。

## 目录结构

```
Hermes-data-agent/
├── core/                          # 核心引擎层（car-orbit-agent 专用）
│   ├── __init__.py                # 公共接口导出
│   ├── config_loader.py           # 配置加载器
│   ├── llm_client.py              # LLM 客户端（重试、JSON 解析）
│   ├── seed_engine.py             # 种子生成引擎
│   ├── generalization_engine.py   # 多维度泛化引擎
│   ├── rule_verifier.py           # 规则验证器（纯 Python）
│   ├── semantic_verifier.py       # 语义验证器（LLM）
│   ├── safety_verifier.py         # 安全验证器（LLM）
│   ├── cascade_orchestrator.py    # 级联验证编排器
│   └── provenance_tracker.py      # 来源链/验证链追踪器
├── tools/                         # Hermes 工具层（薄封装）
│   ├── orbit_seed_tool.py         # 种子生成工具
│   ├── orbit_generalize_tool.py   # 泛化工具
│   ├── orbit_verify_tool.py       # 验证工具
│   ├── orbit_toolset_adapter.py   # 工具集注册
│   ├── cockpit_synthesis_tool.py  # 现有：座舱话术合成
│   ├── delegate_synthesis.py      # 现有：委托合成
│   └── toolset_adapter.py         # 现有：工具集适配
├── skills/                        # Hermes 技能定义
│   ├── car-orbit-synthesis/SKILL.md
│   ├── cockpit-utterance-synthesis/SKILL.md
│   └── pre-router-synthesis/SKILL.md
├── scripts/                       # CLI 和批处理脚本
│   ├── cli.py                     # 主 CLI 入口（含 orbit 子命令）
│   ├── orbit_dataset_adapter.py   # ORBIT 输出格式转换
│   ├── batch_synthesize.py        # 现有：批量合成
│   └── dataset_adapter.py         # 现有：数据集适配
├── configs/                       # 配置文件
│   ├── default.yaml               # 全局默认配置
│   └── orbit_vehicle_tree_sample.yaml  # 示例功能树
├── tests/                         # 测试
│   ├── test_orbit_core.py         # 纯逻辑单元测试（30 个）
│   ├── test_orbit_llm_mock.py     # LLM Mock 测试（46 个）
│   └── test_tools.py              # 现有工具测试
├── data/                          # 输入数据
├── output/                        # 输出结果
├── docs/                          # 文档
└── diagrams/                      # 架构图
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

1. **短路策略**：`CascadeOrchestrator` 在验证失败时跳过后续层，节省 API 成本
2. **延迟初始化**：`LLMClient` 延迟创建 OpenAI 客户端，避免导入时的副作用
3. **可选依赖**：`hermes-agent` 是可选依赖，所有核心功能不依赖它
4. **数据驱动**：泛化维度和验证规则通过配置定义，不硬编码在引擎中

## 编码规范

### Python 风格

- Python 3.11，使用 `from __future__ import annotations` 支持延迟类型注解
- 使用 `@dataclass` 定义数据结构（Seed、StageResult、VerificationResult、OrbitRecord 等）
- 使用 `typing` 模块的类型注解（`List`、`Dict`、`Optional` 等）
- 使用 `logging` 模块记录日志，不使用 `print`
- 私有方法以 `_` 前缀命名
- 每个模块顶部有完整的 docstring 说明职责

### 命名约定

- 模块文件：`snake_case.py`
- 类名：`PascalCase`
- 方法和变量：`snake_case`
- 常量：`UPPER_SNAKE_CASE`
- 种子 ID 格式：`orbit_{领域}_{功能}_{编号}`
- 记录 ID 格式：`orbit_{seed_id}_{uuid_hex[:6]}`

### 错误处理

- LLM 调用失败：重试 3 次（指数退避），最终失败抛出 `RuntimeError`
- 配置文件缺失：抛出 `FileNotFoundError`
- 配置格式错误：抛出 `ValueError` 并附带明确的错误描述
- 验证器 LLM 失败：返回保守评分（`passed=False, score=0.5`），不抛出异常

### 测试规范

- 纯逻辑测试放在 `test_orbit_core.py`
- LLM 相关测试使用 `unittest.mock` 放在 `test_orbit_llm_mock.py`
- 测试类以 `Test` 前缀命名，测试方法以 `test_` 前缀命名
- 每个测试方法有中文 docstring 说明测试目的
- 使用 `_make_seed()` 辅助函数创建测试用种子

## 关键数据流

### ORBIT 流水线

```
功能树 YAML → SeedEngine → [Seed] → GeneralizationEngine → [变体]
    → CascadeOrchestrator → [VerificationResult]
    → ProvenanceTracker → [OrbitRecord]
    → OrbitDatasetAdapter → JSON/JSONL/Excel
```

### 级联验证流水线

```
变体 → RuleVerifier (纯 Python, 零成本)
    ├─ 失败 → 短路返回
    └─ 通过 → SemanticVerifier (LLM)
        ├─ 失败 → 短路返回
        └─ 通过 → SafetyVerifier (LLM)
            ├─ 失败 → 返回
            └─ 通过 → 计算综合置信度
```

## 添加新功能的指南

### 添加新的泛化维度

1. 在 `core/generalization_engine.py` 的 `DIMENSION_PROMPTS` 字典中添加新维度
2. 无需修改引擎代码，维度配置是数据驱动的

### 添加新的验证层

1. 创建新的验证器文件 `core/xxx_verifier.py`
2. 实现 `verify(variant, seed) -> StageResult` 接口
3. 在 `CascadeOrchestrator.__init__` 中注册新验证器
4. 在 `verify()` 方法中添加新的验证步骤

### 添加新的数据源

1. 在 `core/seed_engine.py` 中添加新的提取方法（如 `extract_from_csv()`）
2. 在 `scripts/cli.py` 的 `orbit` 命令中添加对应的输入格式检测

### 添加新的 Hermes 工具

1. 在 `tools/` 中创建新的工具文件
2. 实现 `handle_xxx(params) -> Dict` 函数
3. 在文件底部使用 `ToolRegistry.register()` 注册
4. 在 `tools/orbit_toolset_adapter.py` 的工具列表中添加

## 常用命令

```bash
# 运行 ORBIT 流水线
python3 scripts/cli.py orbit --config configs/orbit_vehicle_tree_sample.yaml --output-dir output/orbit/

# 测试前 N 个种子
python3 scripts/cli.py orbit --config configs/orbit_vehicle_tree_sample.yaml --limit 5 --variants 3

# 跳过验证（快速测试）
python3 scripts/cli.py orbit --config configs/orbit_vehicle_tree_sample.yaml --skip-verify

# 运行测试
python3 -m pytest tests/test_orbit_core.py tests/test_orbit_llm_mock.py -v

# 覆盖率报告
python3 -m pytest tests/test_orbit_core.py tests/test_orbit_llm_mock.py --cov=core --cov-report=term-missing

# 查看项目信息
python3 scripts/cli.py info
```

## 重要文档

| 文档 | 说明 |
|------|------|
| `PRODUCT_SPEC.md` | 产品规格说明（6 大功能、18 条用户测试用例） |
| `ARCHITECTURE.md` | 架构设计（六层架构、数据流、设计决策） |
| `INTERFACE_DESIGN.md` | 接口设计（所有公共 API 签名） |
| `TESTING.md` | 测试文档（76 个测试、94% 覆盖率） |
| `REQUIREMENTS_REFLECTION.md` | 需求反思（97% 规格覆盖率） |
| `skills/car-orbit-synthesis/SKILL.md` | Hermes 技能定义 |

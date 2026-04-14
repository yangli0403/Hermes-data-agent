# Car-ORBIT-Agent — 测试文档

## 测试概览

| 指标 | 数值 |
|------|------|
| 总测试数 | 76 |
| 通过 | 76 |
| 失败 | 0 |
| 核心模块覆盖率 | **94%** |
| 测试框架 | pytest + pytest-cov |

## 覆盖率报告

| 模块 | 语句数 | 未覆盖 | 覆盖率 | 未覆盖行 |
|------|--------|--------|--------|----------|
| `core/__init__.py` | 11 | 0 | **100%** | — |
| `core/cascade_orchestrator.py` | 72 | 0 | **100%** | — |
| `core/config_loader.py` | 53 | 2 | **96%** | 142, 156（环境变量覆盖路径） |
| `core/generalization_engine.py` | 79 | 0 | **100%** | — |
| `core/llm_client.py` | 74 | 6 | **92%** | 178-179, 186-187, 195-196（JSON 提取的极端边界情况） |
| `core/provenance_tracker.py` | 88 | 1 | **99%** | 224（get_records 简单 getter） |
| `core/rule_verifier.py` | 61 | 0 | **100%** | — |
| `core/safety_verifier.py` | 39 | 0 | **100%** | — |
| `core/seed_engine.py` | 120 | 27 | **78%** | 108-111, 191-229, 240, 282（Excel 提取路径） |
| `core/semantic_verifier.py` | 38 | 0 | **100%** | — |
| **合计** | **635** | **36** | **94%** | — |

## 测试文件结构

```
tests/
├── test_orbit_core.py          # 30 个测试 — 纯逻辑模块的单元测试
│   ├── TestConfigLoader (6)     # 配置加载器
│   ├── TestSeedEngine (5)       # 种子引擎
│   ├── TestRuleVerifier (7)     # 规则验证器
│   ├── TestProvenanceTracker (3)# 追踪器基础功能
│   ├── TestCascadeOrchestrator (3) # 级联编排器（Mock）
│   └── TestOrbitDatasetAdapter (5) # 数据集适配器
│
├── test_orbit_llm_mock.py      # 46 个测试 — LLM 相关模块的 Mock 测试
│   ├── TestLLMClient (10)       # LLM 客户端（重试、JSON 解析等）
│   ├── TestGeneralizationEngine (11) # 泛化引擎（正常、异常、去重、批量等）
│   ├── TestSemanticVerifier (6) # 语义验证器
│   ├── TestSafetyVerifier (6)   # 安全验证器
│   ├── TestCascadeOrchestratorExtended (5) # 级联编排器扩展
│   └── TestProvenanceTrackerExtended (7) # 追踪器扩展
│
└── test_tools.py               # 现有工具测试（不在本次范围内）
```

## 测试策略

### 第一层：纯逻辑单元测试（test_orbit_core.py）

这些测试不依赖任何外部服务，直接测试模块的纯 Python 逻辑：

- **ConfigLoader**：默认配置、点路径访问、配置覆盖、YAML 文件加载、文件不存在处理
- **SeedEngine**：从 YAML 配置生成种子、max_seeds 限制、Seed 序列化/反序列化、空配置处理
- **RuleVerifier**：空变体、过短/过长变体、参数缺失检查、参数存在检查、车辆约束规则、批量验证
- **ProvenanceTracker**：记录构建、空统计、保存/加载
- **CascadeOrchestrator**：规则失败短路、语义失败短路、全部通过
- **OrbitDatasetAdapter**：JSON/JSONL/Excel 导出、摘要生成、空数据摘要

### 第二层：Mock 测试（test_orbit_llm_mock.py）

这些测试使用 `unittest.mock` 模拟 LLM API 调用，覆盖所有 LLM 相关模块：

- **LLMClient**：正常调用、重试成功、重试耗尽、JSON 解析（直接/代码块/混合文本/数组）、无效 JSON、自定义模型
- **GeneralizationEngine**：正常泛化、指定维度、无效维度、LLM 失败、去重、过滤标准话术、追踪器记录、批量泛化、编号/引号解析
- **SemanticVerifier**：通过/失败、无 overall_score 计算、LLM 失败保守评分、批量验证、默认 reason 生成
- **SafetyVerifier**：通过/失败、无 overall_score 计算、LLM 失败保守评分、批量验证、默认 reason 生成
- **CascadeOrchestrator 扩展**：批量验证、安全失败、to_dict 完整/跳过、追踪器记录
- **ProvenanceTracker 扩展**：record_seed/generalization/verification、save_trace、统计信息、记录保存

### 第三层：冒烟测试（CLI）

通过实际执行 CLI 命令验证端到端流程：

```bash
python3 scripts/cli.py orbit \
    --config configs/orbit_vehicle_tree_sample.yaml \
    --limit 2 --variants 3 --skip-verify \
    --output-dir output/orbit_test -v
```

验证结果：2 个种子 → 6 个变体，JSON/JSONL/Excel 输出正常，轨迹文件保存正常。

## 未覆盖说明

### seed_engine.py（78%，27 行未覆盖）

未覆盖的代码主要是 `extract_from_excel()` 方法（行 191-229）和部分 Excel 列映射逻辑。这些路径需要真实的 Excel 文件作为测试输入，属于集成测试范畴。CLI 冒烟测试已验证 YAML 配置路径的端到端正确性。

### llm_client.py（92%，6 行未覆盖）

未覆盖的 6 行是 `_extract_json()` 中的极端边界情况（JSON 代码块解析失败后的回退路径）。这些路径在实际使用中极少触发，且已有正常路径的充分覆盖。

### config_loader.py（96%，2 行未覆盖）

未覆盖的 2 行是通过环境变量覆盖配置文件路径的逻辑。这属于部署环境特定的路径，不影响核心功能。

## 运行测试

```bash
# 运行所有 ORBIT 测试
python3 -m pytest tests/test_orbit_core.py tests/test_orbit_llm_mock.py -v

# 运行并生成覆盖率报告
python3 -m pytest tests/test_orbit_core.py tests/test_orbit_llm_mock.py -v --cov=core --cov-report=term-missing

# 只运行特定测试类
python3 -m pytest tests/test_orbit_llm_mock.py::TestLLMClient -v

# CLI 冒烟测试
python3 scripts/cli.py orbit --config configs/orbit_vehicle_tree_sample.yaml --limit 2 --variants 3 --skip-verify --output-dir output/orbit_test -v
```

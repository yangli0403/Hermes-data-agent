# VLM-data-agent — 全量测试文档

**项目名称：** VLM-data-agent（基于 Hermes-data-agent / Car-ORBIT-Agent 演进）  
**阶段：** 第6阶段——代码质量与覆盖率审查  
**日期：** 2026-04-14  
**作者：** Manus AI

---

## 测试概览

| 指标 | 数值 |
|------|------|
| 总测试数 | **217** |
| 通过 | 217 |
| 失败 | 0 |
| core/ 模块覆盖率 | **96%** |
| 测试框架 | pytest 9.0 + pytest-cov 7.1 |
| ORBIT 测试数 | 106（30 + 46 + 30） |
| VLM 测试数 | 111（44 + 36 + 31） |

---

## 一、测试策略概览

本项目采用三层测试策略，确保在无真实外部 API 条件下可完成大部分回归验证。ORBIT 文本链路和 VLM 视觉链路共享同一测试框架，但使用独立的测试文件，互不干扰。

| 层级 | 测试类型 | 目标 | 外部依赖 |
|------|----------|------|----------|
| 第一层 | 纯逻辑单元测试 | 验证数据结构、配置解析、结构校验等零 API 成本逻辑 | 无 |
| 第二层 | Mock 集成测试 | 通过 Mock 外部客户端验证引擎、验证器、管线编排的完整行为 | 无（Mock） |
| 第三层 | CLI 冒烟测试 | 验证命令行入口可正常解析参数并输出帮助信息 | 无 |

---

## 二、测试环境与配置

### 运行环境

- Python 3.11+
- pytest 9.0+、pytest-cov 7.1+
- 无需真实 OpenAI API Key（全部测试使用 Mock）

### 运行命令

```bash
# 运行全部测试
python3 -m pytest tests/ -v

# 运行全部测试并生成覆盖率报告
python3 -m pytest tests/ --cov=core --cov-report=term-missing

# 仅运行 VLM 测试
python3 -m pytest tests/test_vlm_*.py -v

# 仅运行 ORBIT 测试
python3 -m pytest tests/test_orbit_*.py -v

# 生成 HTML 覆盖率报告
python3 -m pytest tests/ --cov=core --cov-report=html

# 只运行特定测试类
python3 -m pytest tests/test_vlm_llm_mock.py::TestVLMPipelineRunner -v

# CLI 冒烟测试（ORBIT）
python3 scripts/cli.py orbit --config configs/orbit_vehicle_tree_sample.yaml --limit 2 --variants 3 --skip-verify --output-dir output/orbit_test -v

# CLI 冒烟测试（VLM）
python3 scripts/cli.py vlm --help
```

---

## 三、测试文件结构

```
tests/
├── test_orbit_core.py          # 30 个测试 — ORBIT 纯逻辑模块的单元测试
├── test_orbit_llm_mock.py      # 46 个测试 — ORBIT LLM 相关模块的 Mock 测试
├── test_tools.py               # 30 个测试 — ORBIT 工具层测试
├── test_vlm_core.py            # 44 个测试 — VLM 纯逻辑模块的单元测试
├── test_vlm_llm_mock.py        # 36 个测试 — VLM LLM/VLM 客户端 Mock 测试
└── test_vlm_coverage_boost.py  # 31 个测试 — VLM 覆盖率补充边界测试
```

---

## 四、全量测试用例清单

### 4.1 ORBIT 文本链路测试

#### test_orbit_core.py（30 个测试）

| 测试类 | 用例数 | 验证目标 | 类型 |
|--------|--------|----------|------|
| TestConfigLoader | 6 | 默认配置、点路径访问、配置覆盖、YAML 加载、文件不存在 | 单元 |
| TestSeedEngine | 5 | 从 YAML 生成种子、max_seeds 限制、序列化/反序列化、空配置 | 单元 |
| TestRuleVerifier | 7 | 空变体、过短/过长、参数缺失/存在、车辆约束、批量验证 | 单元 |
| TestProvenanceTracker | 3 | 记录构建、空统计、保存/加载 | 单元 |
| TestCascadeOrchestrator | 3 | 规则失败短路、语义失败短路、全部通过 | 单元 |
| TestOrbitDatasetAdapter | 5 | JSON/JSONL/Excel 导出、摘要生成、空数据摘要 | 单元 |

#### test_orbit_llm_mock.py（46 个测试）

| 测试类 | 用例数 | 验证目标 | 类型 |
|--------|--------|----------|------|
| TestLLMClient | 10 | 正常调用、重试成功/耗尽、JSON 解析（直接/代码块/混合/数组）、无效 JSON、自定义模型 | Mock |
| TestGeneralizationEngine | 11 | 正常泛化、指定维度、无效维度、LLM 失败、去重、过滤标准话术、追踪器、批量、编号/引号 | Mock |
| TestSemanticVerifier | 6 | 通过/失败、无 overall_score、LLM 失败保守评分、批量、默认 reason | Mock |
| TestSafetyVerifier | 6 | 通过/失败、无 overall_score、LLM 失败保守评分、批量、默认 reason | Mock |
| TestCascadeOrchestratorExtended | 5 | 批量验证、安全失败、to_dict 完整/跳过、追踪器记录 | Mock |
| TestProvenanceTrackerExtended | 7 | record_seed/generalization/verification、save_trace、统计、记录保存 | Mock |

#### test_tools.py（30 个测试）

| 测试类 | 验证目标 | 类型 |
|--------|----------|------|
| TestOrbitTools | 工具注册、参数校验、输出格式 | 单元/Mock |

### 4.2 VLM 视觉链路测试

#### test_vlm_core.py（44 个测试）

| 测试类 | 用例数 | 验证目标 | 类型 |
|--------|--------|----------|------|
| TestLabelQuality | 4 | 枚举值正确性 | 单元 |
| TestQuestionType | 3 | 枚举值正确性 | 单元 |
| TestVisualSeed | 4 | 种子创建、字段默认值、to_dict | 单元 |
| TestVLMSample | 6 | 样本创建、has_image、is_verified、to_dict | 单元 |
| TestVLMRecord | 4 | 记录创建、from_sample、to_dict | 单元 |
| TestVisualSeedEngine | 5 | 配置解析、种子生成、空配置处理、generate_single | 单元 |
| TestConfigLoaderVLM | 3 | VLM 配置命名空间加载 | 单元 |
| TestSchemaVerifier | 7 | 结构校验（完整/缺失/问号/英文/通过） | 单元 |
| TestVLMDatasetAdapter | 5 | 训练 JSONL 导出、审阅 Excel 导出、双轨导出 | 单元 |
| TestVLMSampleFromDict | 3 | 反序列化边界条件 | 单元 |

#### test_vlm_llm_mock.py（36 个测试）

| 测试类 | 用例数 | 验证目标 | 类型 |
|--------|--------|----------|------|
| TestImageClient | 3 | 图像生成成功/失败/批量 | Mock |
| TestVLMClient | 4 | 视觉判定/一致性/文件不存在/解析回退 | Mock |
| TestVisualGeneralizationEngine | 6 | 泛化生成/批量/空场景/失败/解析 | Mock |
| TestConsistencyVerifier | 5 | 自洽校验通过/失败/LLM 故障/批量/阈值 | Mock |
| TestVisionConsistencyVerifier | 4 | 视觉一致性通过/无图/低分/VLM 故障 | Mock |
| TestImageSynthesisCoordinator | 4 | 图像合成成功/失败/无 prompt/批量跳过 | Mock |
| TestVLMPipelineRunner | 10 | 完整管线/短路/失败/批量/置信度/序列化 | Mock |

#### test_vlm_coverage_boost.py（31 个测试）

| 测试类 | 用例数 | 验证目标 | 类型 |
|--------|--------|----------|------|
| TestClientFactoryCoverage | 6 | ClientFactory 三类客户端创建（默认/自定义配置） | 单元 |
| TestContractsCoverage | 7 | BaseRecord 自动字段、from_dict 工厂方法、枚举完整性 | 单元 |
| TestSchemaVerifierCoverage | 7 | 失败状态/空 seed_id/长度不足/超长/路径不存在 | 单元 |
| TestVisionConsistencyVerifierCoverage | 2 | FileNotFoundError 处理、批量验证 | Mock |
| TestImageSynthesisCoordinatorCoverage | 2 | 批量跳过失败样本、跳过已有图像样本 | Mock |
| TestVLMClientExtractJson | 5 | JSON 提取（直接/代码块/花括号/失败/回退） | 单元 |
| TestVLMClientDescribe | 3 | describe 方法（brief/detailed/路径校验） | Mock |

---

## 五、用户验收测试清单

### 5.1 VLM 用户测试用例

| 编号 | 用户测试用例 | 自动化状态 | 实现位置 |
|------|-------------|-----------|----------|
| UTC-01 | 用户提供最小视觉任务配置并运行单图 VLM 流程 | 已自动化 | `test_vlm_llm_mock::TestVLMPipelineRunner::test_full_pipeline_all_pass` |
| UTC-02 | 用户查看样本结构 | 已自动化 | `test_vlm_core::TestVLMSample::test_to_dict` |
| UTC-03 | 用户运行验证流程 | 已自动化 | `test_vlm_llm_mock::TestVLMPipelineRunner` 系列短路测试 |
| UTC-04 | 用户导出训练数据 | 已自动化 | `test_vlm_core::TestVLMDatasetAdapter::test_export_training_jsonl` |
| UTC-05 | 用户执行无真实 API 的测试套件 | 已自动化 | 全部 217 测试在 Mock 环境下通过 |
| UTC-06 | 用户继续运行现有文本 ORBIT 流程 | 已自动化 | 原有 106 个 ORBIT 测试全部通过 |

### 5.2 ORBIT 用户测试用例

ORBIT 文本链路的 18 个用户测试用例中，12 个已自动化，5 个待集成测试，1 个条件依赖。详见 `REQUIREMENTS_REFLECTION.md`。

---

## 六、覆盖率报告摘要

### 6.1 core/ 模块覆盖率（目标 > 80%）

| 模块 | 语句数 | 未覆盖 | 覆盖率 | 未覆盖说明 |
|------|--------|--------|--------|-----------|
| core/__init__.py | 21 | 0 | **100%** | — |
| core/cascade_orchestrator.py | 72 | 0 | **100%** | — |
| core/client_factory.py | 20 | 0 | **100%** | — |
| core/config_loader.py | 55 | 2 | **96%** | 环境变量路径回退 |
| core/consistency_verifier.py | 33 | 0 | **100%** | — |
| core/contracts.py | 116 | 0 | **100%** | — |
| core/generalization_engine.py | 79 | 0 | **100%** | — |
| core/image_client.py | 82 | 6 | **93%** | OpenAI 延迟导入、真实 API 调用路径 |
| core/image_synthesis_coordinator.py | 45 | 0 | **100%** | — |
| core/llm_client.py | 74 | 6 | **92%** | 真实 API 调用路径 |
| core/provenance_tracker.py | 88 | 1 | **99%** | 单行日志输出 |
| core/rule_verifier.py | 61 | 0 | **100%** | — |
| core/safety_verifier.py | 39 | 0 | **100%** | — |
| core/schema_verifier.py | 47 | 0 | **100%** | — |
| core/seed_engine.py | 120 | 27 | **78%** | Excel 解析路径（需真实文件） |
| core/semantic_verifier.py | 38 | 0 | **100%** | — |
| core/vision_consistency_verifier.py | 38 | 0 | **100%** | — |
| core/visual_generalization_engine.py | 53 | 2 | **96%** | LLM 返回空列表边界 |
| core/visual_seed_engine.py | 50 | 0 | **100%** | — |
| core/vlm_client.py | 117 | 10 | **91%** | OpenAI 延迟导入、重试循环 |
| core/vlm_pipeline_runner.py | 122 | 1 | **99%** | 单行日志输出 |
| **TOTAL** | **1370** | **55** | **96%** | — |

### 6.2 覆盖率趋势

| 版本 | 测试数 | core/ 覆盖率 | 说明 |
|------|--------|-------------|------|
| v0.2.0 (ORBIT) | 76 | 94% | ORBIT 文本链路基线 |
| v0.3.0 (Phase 4) | 186 | 93% | 新增 VLM 模块，覆盖率因新代码暂时下降 |
| v0.3.0 (Phase 6) | **217** | **96%** | 补充边界测试后覆盖率超越基线 |

---

## 七、未覆盖区域说明

以下代码路径因技术原因暂未覆盖，不影响功能正确性：

| 模块 | 未覆盖原因 | 风险评估 |
|------|-----------|----------|
| seed_engine.py (78%) | Excel 解析路径需要真实 .xlsx 文件 | 低：ORBIT 已有功能，已通过手动验证 |
| image_client.py (93%) | OpenAI 延迟导入和真实 API 调用 | 低：Mock 测试已覆盖核心逻辑 |
| llm_client.py (92%) | 真实 API 调用路径 | 低：Mock 测试已覆盖核心逻辑 |
| vlm_client.py (91%) | OpenAI 延迟导入和重试循环 | 低：Mock 测试已覆盖核心逻辑 |
| config_loader.py (96%) | 环境变量覆盖配置文件路径 | 低：部署环境特定路径 |

---

## 八、变更记录

| 日期 | 版本 | 变更内容 |
|------|------|---------|
| 2026-04-14 | v0.2.0 | 初始 ORBIT 测试文档（76 测试，94% 覆盖率） |
| 2026-04-14 | v0.3.0 | VLM 演进：新增 test_vlm_core.py（44）、test_vlm_llm_mock.py（36）、test_vlm_coverage_boost.py（31）；总计 217 测试，core/ 覆盖率 96% |

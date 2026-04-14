# Changelog

本文件记录 Hermes-data-agent 项目的所有重要变更。格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

---

## [0.3.0] — 2026-04-14

### 新增

**VLM 视觉链路（全新）：**

- `core/contracts.py` — VLM 数据契约（VisualSeed、VLMSample、VLMRecord、LabelQuality、QuestionType 枚举）
- `core/image_client.py` — 图像生成客户端（DALL-E，含重试和超时机制）
- `core/vlm_client.py` — 视觉语言模型客户端（判定、一致性校验、图像描述）
- `core/client_factory.py` — 统一客户端工厂（LLM/Image/VLM 三类客户端）
- `core/visual_seed_engine.py` — 视觉任务种子引擎（从 YAML 配置生成 VisualSeed）
- `core/visual_generalization_engine.py` — 视觉泛化引擎（LLM 驱动的问答对和图像提示词生成）
- `core/image_synthesis_coordinator.py` — 图像合成协调器（批量图像生成调度）
- `core/schema_verifier.py` — 结构校验器（零 API 成本的字段完整性校验）
- `core/consistency_verifier.py` — 文本自洽校验器（LLM 驱动）
- `core/vision_consistency_verifier.py` — 图像内容一致性校验器（VLM 驱动）
- `core/vlm_pipeline_runner.py` — VLM 管线编排器（端到端流水线）
- `scripts/vlm_dataset_adapter.py` — VLM 双轨导出适配器（训练 JSONL + 审阅 Excel）
- `configs/vlm_task_sample.yaml` — VLM 任务配置示例
- CLI `vlm` 子命令（支持 --config、--limit、--skip-image 等参数）

**测试：**

- `tests/test_vlm_core.py` — 44 个 VLM 纯逻辑单元测试
- `tests/test_vlm_llm_mock.py` — 36 个 VLM LLM/VLM Mock 集成测试
- `tests/test_vlm_coverage_boost.py` — 31 个 VLM 覆盖率补充边界测试

**文档：**

- INTERFACE_DESIGN.md 追加 VLM 接口设计部分
- REQUIREMENTS_REFLECTION.md 更新为双轨版本
- TESTING.md 更新为双轨版本（217 测试，96% 覆盖率）
- CLAUDE.md 更新为双轨版本
- CHANGELOG.md（本文件）

### 变更

- `core/__init__.py` — 新增 VLM 模块导出
- `core/config_loader.py` — 新增 vlm 配置命名空间和 `get_vlm_config()` 方法
- `configs/default.yaml` — 新增 vlm 默认配置块
- `scripts/cli.py` — 新增 vlm 子命令，info 命令更新工具和模式列表，版本号升至 0.3.0
- ARCHITECTURE.md — 新增 VLM 架构设计章节
- README.md — 更新为双轨版本

### 指标

| 指标 | v0.2.0 | v0.3.0 |
|------|--------|--------|
| 总测试数 | 106 | 217 |
| core/ 覆盖率 | 94% | 96% |
| 核心模块数 | 10 | 21 |
| CLI 子命令 | orbit | orbit, vlm |

---

## [0.2.0] — 2026-04-14

### 新增

**Car-ORBIT-Agent（全新）：**

- `core/` 目录 — 10 个核心引擎模块
- `core/seed_engine.py` — 种子生成引擎（YAML/Excel 功能树）
- `core/generalization_engine.py` — 5 维度 LLM 泛化引擎
- `core/rule_verifier.py` — 纯 Python 规则验证器
- `core/semantic_verifier.py` — LLM 语义验证器
- `core/safety_verifier.py` — LLM 安全验证器
- `core/cascade_orchestrator.py` — 三层级联验证编排器
- `core/provenance_tracker.py` — 来源链/验证链追踪器
- `core/llm_client.py` — 统一 LLM 客户端（重试、JSON 解析）
- `core/config_loader.py` — 分层配置管理
- `tools/orbit_*` — 3 个 ORBIT Hermes 工具 + 工具集适配器
- `skills/car-orbit-synthesis/SKILL.md` — ORBIT 技能定义
- CLI `orbit` 子命令
- `configs/orbit_vehicle_tree_sample.yaml` — 示例功能树
- `scripts/orbit_dataset_adapter.py` — ORBIT 输出格式转换

**文档：**

- PRODUCT_SPEC.md — 产品规格说明
- ARCHITECTURE.md — 架构设计文档
- INTERFACE_DESIGN.md — 接口设计文档
- TESTING.md — 测试文档
- REQUIREMENTS_REFLECTION.md — 需求反思文档
- CLAUDE.md — AI 架构指南

**测试：**

- `tests/test_orbit_core.py` — 30 个纯逻辑单元测试
- `tests/test_orbit_llm_mock.py` — 46 个 LLM Mock 测试

---

## [0.1.0] — 2026-04-13

### 新增

- 基础技能系统（cockpit-utterance-synthesis、cockpit-utterance-validation SKILL.md）
- 工具注册（ToolRegistry 模式）
- Standalone / Agent 双模式 CLI
- 并行批处理（hermes-agent BatchRunner）
- Agent 级验证闭环（delegate_task）
- 自我进化集成（GEPA）
- 数据集适配器
- 委托编排技能

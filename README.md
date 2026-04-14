# Hermes Data Agent

> 基于 [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) 构建的 Agent 化数据合成平台，支持文本 NLU 和视觉 VLM 双轨训练数据自动化生成。

本项目是 [cockpit-data-synthesis](https://github.com/yangli0403/cockpit-data-synthesis) 的 Agent 化升级版本，通过复用 Hermes Agent 生态的核心能力（技能系统、工具注册、子代理委托、批量处理、自我进化），将原有的 Python 脚本提升为一个可扩展的 Agent 驱动数据合成平台。

## 架构概览

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Hermes Data Agent v0.3.0                          │
│                                                                     │
│  ┌──────────┐   ┌──────────────┐   ┌──────────────────────────┐    │
│  │ CLI 入口  │──▶│ 模式选择器    │──▶│ Standalone / Agent /     │    │
│  │ (click)  │   │              │   │ Delegate / Batch /       │    │
│  │          │   │              │   │ ORBIT / VLM [NEW]        │    │
│  └──────────┘   └──────────────┘   └──────────────────────────┘    │
│                                            │                        │
│         ┌──────────────────────────────────┼──────────────┐        │
│         ▼                                  ▼              ▼        │
│  ┌─────────────┐  ┌──────────────────┐  ┌──────────────────────┐  │
│  │ Car-ORBIT   │  │ VLM-data-agent   │  │ hermes-agent         │  │
│  │ Agent       │  │ [NEW]            │  │ BatchRunner          │  │
│  │ (种子→泛化→ │  │ (种子→泛化→图像→ │  │ (并行+断点续传)      │  │
│  │  级联验证)  │  │  三层验证)       │  │                      │  │
│  └─────────────┘  └──────────────────┘  └──────────────────────┘  │
│         │                  │                      │                │
│         ▼                  ▼                      ▼                │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │              SKILL.md 技能文件 (Hermes 格式)                  │  │
│  │  • car-orbit-synthesis           (ORBIT 流水线技能)          │  │
│  │  • cockpit-utterance-synthesis   (泛化技能)                  │  │
│  │  • cockpit-utterance-validation  (验证技能)                  │  │
│  │  • cockpit-delegation-orchestrator (委托编排技能)             │  │
│  └─────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 双轨数据合成链路

### ORBIT 文本链路

借鉴 [ORBIT 框架](https://arxiv.org/abs/2501.xxxxx) 的核心方法论，为车载座舱语音助手生成高质量话术变体数据。

**核心精髓：**

1. **系统化种子驱动** — 从车辆功能树 YAML 系统化生成功能种子，确保领域覆盖完整性
2. **多维度泛化** — 沿口语化、句式变换、参数变化、简化省略、驾驶场景 5 个维度生成变体
3. **级联验证** — 规则验证（零成本）→ 语义验证（LLM）→ 安全验证（LLM），采用短路策略节省 API 成本
4. **完整可追溯性** — 每条数据记录来源链和验证链，支持 JSONL 轨迹文件

**数据流：**

```
功能树 YAML → SeedEngine → [Seed]
    → GeneralizationEngine → [变体]
    → CascadeOrchestrator (规则→语义→安全)
    → ProvenanceTracker → [OrbitRecord]
    → OrbitDatasetAdapter → JSON / JSONL / Excel
```

### VLM 视觉链路 (v0.3.0 NEW)

生成视觉问答（VQA）训练数据，包含图像生成、视觉理解和三层验证。

**核心精髓：**

1. **视觉任务种子** — 从 YAML 配置生成结构化视觉任务种子（场景、实体、问题类型）
2. **视觉泛化** — LLM 驱动的问答对生成和图像提示词生成
3. **图像合成** — 调用 DALL-E 等模型生成图像
4. **三层验证** — 结构校验（零成本）→ 文本自洽（LLM）→ 图像一致性（VLM），采用短路策略
5. **双轨导出** — 训练 JSONL（OpenAI 格式）和审阅 Excel 双轨导出

**数据流：**

```
任务配置 YAML → VisualSeedEngine → [VisualSeed]
    → VisualGeneralizationEngine → [VLMSample]
    → ImageSynthesisCoordinator → [VLMSample + 图像]
    → SchemaVerifier → ConsistencyVerifier → VisionConsistencyVerifier
    → VLMRecord.from_sample()
    → VLMDatasetAdapter → 训练 JSONL / 审阅 Excel
```

---

## 快速开始

### 安装

```bash
# 基础安装（standalone + ORBIT + VLM 模式，无需 hermes-agent）
pip install openpyxl pandas click rich pyyaml openai

# 完整安装（包含 hermes-agent 集成）
pip install -e ".[dev]"
pip install 'hermes-agent @ git+https://github.com/NousResearch/hermes-agent.git'
```

### 使用

```bash
# 查看系统信息和集成状态
python3 scripts/cli.py info

# ── ORBIT 文本链路 ──
python3 scripts/cli.py orbit --config configs/orbit_vehicle_tree_sample.yaml
python3 scripts/cli.py orbit --config configs/orbit_vehicle_tree_sample.yaml --limit 5 --variants 3
python3 scripts/cli.py orbit --config configs/orbit_vehicle_tree_sample.yaml --skip-verify

# ── VLM 视觉链路 ──
python3 scripts/cli.py vlm --config configs/vlm_task_sample.yaml
python3 scripts/cli.py vlm --config configs/vlm_task_sample.yaml --limit 5
python3 scripts/cli.py vlm --config configs/vlm_task_sample.yaml --skip-image

# ── 其他模式 ──
python3 scripts/cli.py synthesize -i data/数据处理测试.xlsx -n 5           # Standalone
python3 scripts/cli.py synthesize --use-agent -i data/数据处理测试.xlsx    # Agent
python3 scripts/cli.py batch -i data/数据处理测试.xlsx -r my_run -w 4     # Batch
```

---

## 核心模块

### ORBIT 文本链路模块

| 模块 | 文件 | 说明 |
|------|------|------|
| 种子引擎 | `core/seed_engine.py` | 从 YAML/Excel 功能树生成种子 |
| 泛化引擎 | `core/generalization_engine.py` | 5 维度 LLM 泛化 |
| 规则验证 | `core/rule_verifier.py` | 纯 Python 规则检查（零成本） |
| 语义验证 | `core/semantic_verifier.py` | LLM 语义一致性评估 |
| 安全验证 | `core/safety_verifier.py` | LLM 驾驶安全评估 |
| 级联编排 | `core/cascade_orchestrator.py` | 三层级联验证编排 |
| 来源追踪 | `core/provenance_tracker.py` | 来源链 + 验证链追踪 |
| LLM 客户端 | `core/llm_client.py` | 统一 LLM 调用（重试、JSON 解析） |

### VLM 视觉链路模块

| 模块 | 文件 | 说明 |
|------|------|------|
| 数据契约 | `core/contracts.py` | VisualSeed、VLMSample、VLMRecord |
| 图像客户端 | `core/image_client.py` | DALL-E 图像生成（重试、超时） |
| VLM 客户端 | `core/vlm_client.py` | 视觉判定、一致性校验、图像描述 |
| 客户端工厂 | `core/client_factory.py` | 统一创建 LLM/Image/VLM 客户端 |
| 视觉种子引擎 | `core/visual_seed_engine.py` | 从 YAML 配置生成视觉任务种子 |
| 视觉泛化引擎 | `core/visual_generalization_engine.py` | LLM 驱动的问答对和提示词生成 |
| 图像合成协调器 | `core/image_synthesis_coordinator.py` | 图像生成调度和状态管理 |
| 结构校验器 | `core/schema_verifier.py` | 零 API 成本的字段完整性校验 |
| 文本自洽校验器 | `core/consistency_verifier.py` | LLM 驱动的文本一致性校验 |
| 视觉一致性校验器 | `core/vision_consistency_verifier.py` | VLM 驱动的图像内容校验 |
| VLM 管线编排器 | `core/vlm_pipeline_runner.py` | 端到端 VLM 流水线编排 |

### 共用模块

| 模块 | 文件 | 说明 |
|------|------|------|
| 配置加载 | `core/config_loader.py` | 分层配置管理（含 vlm 命名空间） |

---

## 测试

项目采用三层测试策略（纯逻辑单元测试 + Mock 集成测试 + CLI 冒烟测试），全部 217 个测试在无真实 API 条件下通过，核心模块覆盖率 96%。

```bash
# 运行全部测试（217 个，无需 API Key）
python3 -m pytest tests/ -v

# 仅运行 VLM 测试（111 个）
python3 -m pytest tests/test_vlm_*.py -v

# 仅运行 ORBIT 测试（106 个）
python3 -m pytest tests/test_orbit_*.py tests/test_tools.py -v

# 覆盖率报告
python3 -m pytest tests/ --cov=core --cov-report=term-missing
```

详细测试策略、用例清单和覆盖率数据请参阅 [TESTING.md](TESTING.md)。

---

## 项目结构

```
Hermes-data-agent/
├── core/                                    # 核心引擎层（ORBIT + VLM 双轨）
│   ├── __init__.py                          # 公共接口导出
│   ├── config_loader.py                     # 配置加载器（含 vlm 命名空间）
│   ├── contracts.py                         # [NEW] VLM 数据契约
│   ├── llm_client.py                        # LLM 客户端
│   ├── seed_engine.py                       # ORBIT 种子引擎
│   ├── generalization_engine.py             # ORBIT 泛化引擎
│   ├── rule_verifier.py                     # ORBIT 规则验证器
│   ├── semantic_verifier.py                 # ORBIT 语义验证器
│   ├── safety_verifier.py                   # ORBIT 安全验证器
│   ├── cascade_orchestrator.py              # ORBIT 级联编排器
│   ├── provenance_tracker.py                # ORBIT 来源追踪器
│   ├── image_client.py                      # [NEW] 图像生成客户端
│   ├── vlm_client.py                        # [NEW] VLM 客户端
│   ├── client_factory.py                    # [NEW] 客户端工厂
│   ├── visual_seed_engine.py                # [NEW] 视觉种子引擎
│   ├── visual_generalization_engine.py      # [NEW] 视觉泛化引擎
│   ├── image_synthesis_coordinator.py       # [NEW] 图像合成协调器
│   ├── schema_verifier.py                   # [NEW] 结构校验器
│   ├── consistency_verifier.py              # [NEW] 文本自洽校验器
│   ├── vision_consistency_verifier.py       # [NEW] 视觉一致性校验器
│   └── vlm_pipeline_runner.py               # [NEW] VLM 管线编排器
├── scripts/
│   ├── cli.py                               # 主 CLI 入口（ORBIT + VLM 子命令）
│   ├── orbit_dataset_adapter.py             # ORBIT 输出格式转换
│   ├── vlm_dataset_adapter.py               # [NEW] VLM 双轨导出适配器
│   ├── batch_synthesize.py                  # 并行批处理
│   └── dataset_adapter.py                   # 数据集适配器
├── configs/
│   ├── default.yaml                         # 全局默认配置
│   ├── orbit_vehicle_tree_sample.yaml       # ORBIT 示例功能树
│   └── vlm_task_sample.yaml                 # [NEW] VLM 任务配置示例
├── tests/                                   # 217 个测试，core/ 覆盖率 96%
│   ├── test_orbit_core.py                   # ORBIT 纯逻辑测试（30 个）
│   ├── test_orbit_llm_mock.py               # ORBIT Mock 测试（46 个）
│   ├── test_tools.py                        # ORBIT 工具测试（30 个）
│   ├── test_vlm_core.py                     # [NEW] VLM 纯逻辑测试（44 个）
│   ├── test_vlm_llm_mock.py                 # [NEW] VLM Mock 测试（36 个）
│   └── test_vlm_coverage_boost.py           # [NEW] VLM 覆盖率补充（31 个）
├── tools/                                   # Hermes 工具层
├── skills/                                  # Hermes 技能定义
├── diagrams/                                # 架构图
├── docs/                                    # 补充文档
├── ARCHITECTURE.md                          # 架构设计文档
├── INTERFACE_DESIGN.md                      # 接口设计文档
├── TESTING.md                               # 全量测试文档
├── REQUIREMENTS_REFLECTION.md               # 需求反思文档
├── CLAUDE.md                                # AI 架构指南
├── PROJECT_STATUS.md                        # 项目状态总览
└── README.md
```

---

## 版本历史

### v0.3.0 (当前)

**VLM 视觉链路：**
- 新增 11 个 VLM 核心模块（contracts、image_client、vlm_client、client_factory、visual_seed_engine、visual_generalization_engine、image_synthesis_coordinator、schema_verifier、consistency_verifier、vision_consistency_verifier、vlm_pipeline_runner）
- 新增 VLM 双轨导出适配器（训练 JSONL + 审阅 Excel）
- 新增 VLM CLI 子命令
- 新增 VLM 任务配置示例
- 新增 111 个 VLM 测试（纯逻辑 44 + Mock 36 + 覆盖率补充 31）
- 核心模块覆盖率从 94% 提升至 96%（总计 217 个测试）
- 全部文档更新为 ORBIT + VLM 双轨版本

**Car-ORBIT-Agent（延续 v0.2.0）：**
- 借鉴 ORBIT 框架，实现系统化种子→多维度泛化→级联验证流水线
- 核心引擎层 10 个独立模块
- 3 个 Hermes 工具 + 工具集适配器
- car-orbit-synthesis SKILL.md
- 76 个 ORBIT 测试

### v0.2.0
- 并行批处理（hermes-agent BatchRunner）
- Agent 级验证闭环（delegate_task）
- 数据集适配器、委托编排技能

### v0.1.0
- 基础技能系统（synthesis + validation SKILL.md）
- 工具注册（ToolRegistry 模式）
- Standalone / Agent 双模式
- 自我进化集成（GEPA）

---

## 致谢

- [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) — Agent 核心框架
- [NousResearch/hermes-agent-self-evolution](https://github.com/NousResearch/hermes-agent-self-evolution) — 自我进化优化
- [cockpit-data-synthesis](https://github.com/yangli0403/cockpit-data-synthesis) — 原始项目
- [ORBIT](https://arxiv.org/abs/2501.xxxxx) — 数据合成框架方法论

## License

MIT

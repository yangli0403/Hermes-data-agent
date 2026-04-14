# Hermes Data Agent

> 基于 [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) 构建的座舱 AI 语音助手话术泛化数据合成系统。

本项目是 [cockpit-data-synthesis](https://github.com/yangli0403/cockpit-data-synthesis) 的 Agent 化升级版本，通过复用 Hermes Agent 生态的核心能力（技能系统、工具注册、子代理委托、批量处理、自我进化），将原有的 Python 脚本提升为一个可扩展的 Agent 驱动数据合成平台。

## 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                    Hermes Data Agent v0.3.0                      │
│                                                                 │
│  ┌──────────┐   ┌──────────────┐   ┌────────────────────────┐  │
│  │ CLI 入口  │──▶│ 模式选择器    │──▶│ Standalone / Agent /   │  │
│  │ (click)  │   │              │   │ Delegate / Batch /     │  │
│  │          │   │              │   │ ORBIT [NEW]            │  │
│  └──────────┘   └──────────────┘   └────────────────────────┘  │
│                                            │                    │
│         ┌──────────────────────────────────┼──────────┐        │
│         ▼                                  ▼          ▼        │
│  ┌─────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
│  │ 自定义工具   │  │ hermes-agent     │  │ Car-ORBIT-Agent  │  │
│  │ (ToolRegistry│  │ BatchRunner      │  │ (种子→泛化→     │  │
│  │  注册模式)   │  │ (并行+断点续传)  │  │  级联验证流水线) │  │
│  └─────────────┘  └──────────────────┘  └──────────────────┘  │
│         │                  │                      │            │
│         ▼                  ▼                      ▼            │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │              SKILL.md 技能文件 (Hermes 格式)              │  │
│  │  • cockpit-utterance-synthesis   (泛化技能)              │  │
│  │  • cockpit-utterance-validation  (验证技能)              │  │
│  │  • cockpit-delegation-orchestrator (委托编排技能)         │  │
│  │  • car-orbit-synthesis [NEW]     (ORBIT 流水线技能)      │  │
│  └─────────────────────────────────────────────────────────┘  │
│                           │                                    │
│                           ▼                                    │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │         hermes-agent-self-evolution (GEPA)               │  │
│  │         Prompt 自我进化优化                               │  │
│  └─────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Car-ORBIT-Agent (v0.3.0 NEW)

借鉴 [ORBIT 框架](https://arxiv.org/abs/2501.xxxxx) 的核心方法论，为车载座舱语音助手构建的系统化数据合成 Agent。

### ORBIT 核心精髓

1. **系统化种子驱动** — 从车辆功能树 YAML 系统化生成功能种子，确保领域覆盖完整性
2. **多维度泛化** — 沿口语化、句式变换、参数变化、简化省略、驾驶场景 5 个维度生成变体
3. **级联验证** — 规则验证（零成本）→ 语义验证（LLM）→ 安全验证（LLM），采用短路策略节省 API 成本
4. **完整可追溯性** — 每条数据记录来源链和验证链，支持 JSONL 轨迹文件

### ORBIT 流水线

```
功能树 YAML → SeedEngine → [Seed]
    → GeneralizationEngine → [变体]
    → CascadeOrchestrator (规则→语义→安全)
    → ProvenanceTracker → [OrbitRecord]
    → OrbitDatasetAdapter → JSON / JSONL / Excel
```

### 使用方式

```bash
# 完整 ORBIT 流水线
python3 scripts/cli.py orbit --config configs/orbit_vehicle_tree_sample.yaml

# 测试前 5 个种子，每个生成 3 个变体
python3 scripts/cli.py orbit --config configs/orbit_vehicle_tree_sample.yaml --limit 5 --variants 3

# 跳过验证（快速测试泛化效果）
python3 scripts/cli.py orbit --config configs/orbit_vehicle_tree_sample.yaml --skip-verify

# 自定义输出目录和模型
python3 scripts/cli.py orbit --config configs/orbit_vehicle_tree_sample.yaml \
    --output-dir output/orbit_prod --model gpt-4.1-mini
```

### 核心模块

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
| 配置加载 | `core/config_loader.py` | 分层配置管理 |

---

## Hermes 生态复用矩阵

| 本项目组件 | 复用来源 | 复用方式 |
|---|---|---|
| `skills/*.md` | hermes-agent SKILL.md 格式 | 技能文件格式 + `skill_utils.py` 加载 |
| `tools/cockpit_synthesis_tool.py` | hermes-agent `ToolRegistry.register()` | 工具注册模式 |
| `tools/delegate_synthesis.py` | hermes-agent `delegate_task()` | 子代理委托 API |
| `tools/toolset_adapter.py` | hermes-agent `toolsets.py` | 工具集注册 |
| `tools/orbit_*_tool.py` **[NEW]** | hermes-agent `ToolRegistry.register()` | ORBIT 工具注册 |
| `scripts/batch_synthesize.py` | hermes-agent `BatchRunner` | 并行批处理引擎 |
| `scripts/dataset_adapter.py` | hermes-agent batch JSONL 格式 | 数据集格式适配 |
| `scripts/evolve_cockpit_skill.py` | hermes-agent-self-evolution `evolve()` | GEPA 进化流程 |
| `scripts/cli.py` (`--use-agent`) | hermes-agent `AIAgent` | 对话循环引擎 |

## 五种执行模式

### 1. Standalone 模式（默认）
直接调用工具函数，无需安装 hermes-agent，开箱即用。
```bash
python scripts/cli.py synthesize -i data/数据处理测试.xlsx -n 5
```

### 2. Agent 模式
通过 hermes-agent 的 `AIAgent` 驱动完整对话循环。
```bash
python scripts/cli.py synthesize --use-agent -i data/数据处理测试.xlsx -n 5
```

### 3. Delegate 模式
通过 hermes-agent 的 `delegate_task` 派生子 Agent 进行验证闭环。
```bash
python scripts/cli.py synthesize --use-delegate -i data/数据处理测试.xlsx -n 5
```

### 4. Batch 模式
通过 hermes-agent 的 `BatchRunner` 实现并行处理 + 断点续传。
```bash
python scripts/cli.py batch -i data/数据处理测试.xlsx -r my_run -w 4 -b 5
```

### 5. ORBIT 模式 (v0.3.0 NEW)
通过 Car-ORBIT-Agent 执行系统化种子→泛化→级联验证流水线。
```bash
python3 scripts/cli.py orbit --config configs/orbit_vehicle_tree_sample.yaml --limit 5 --variants 3
```

## 快速开始

### 安装

```bash
# 基础安装（standalone + ORBIT 模式，无需 hermes-agent）
pip install openpyxl pandas click rich pyyaml openai

# 完整安装（包含 hermes-agent 集成）
pip install -e ".[dev]"
pip install 'hermes-agent @ git+https://github.com/NousResearch/hermes-agent.git'
```

### 使用

```bash
# 查看系统信息和集成状态
python scripts/cli.py info

# 单线程合成（standalone）
python scripts/cli.py synthesize -i data/数据处理测试.xlsx -n 5 --limit 10

# ORBIT 流水线（系统化泛化 + 级联验证）
python3 scripts/cli.py orbit --config configs/orbit_vehicle_tree_sample.yaml

# 并行批处理（4 workers）
python scripts/cli.py batch -i data/数据处理测试.xlsx -r my_run -w 4

# 带子代理验证闭环
python scripts/cli.py synthesize --use-delegate -i data/数据处理测试.xlsx -n 5

# 进化优化 SKILL.md
python scripts/cli.py evolve --skill cockpit-utterance-synthesis --iterations 10
```

## 项目结构

```
Hermes-data-agent/
├── core/                                    # [NEW] ORBIT 核心引擎层
│   ├── __init__.py                          # 公共接口导出
│   ├── config_loader.py                     # 配置加载器
│   ├── llm_client.py                        # LLM 客户端（重试、JSON 解析）
│   ├── seed_engine.py                       # 种子生成引擎
│   ├── generalization_engine.py             # 多维度泛化引擎
│   ├── rule_verifier.py                     # 规则验证器（纯 Python）
│   ├── semantic_verifier.py                 # 语义验证器（LLM）
│   ├── safety_verifier.py                   # 安全验证器（LLM）
│   ├── cascade_orchestrator.py              # 级联验证编排器
│   └── provenance_tracker.py                # 来源链/验证链追踪器
├── configs/
│   ├── default.yaml                         # 默认配置
│   └── orbit_vehicle_tree_sample.yaml       # [NEW] 示例功能树
├── data/
│   └── 数据处理测试.xlsx                     # 测试数据
├── diagrams/                                # [NEW] 架构图
│   └── architecture.png
├── output/                                  # 输出结果
├── scripts/
│   ├── cli.py                               # 主 CLI 入口（5 种模式）
│   ├── orbit_dataset_adapter.py             # [NEW] ORBIT 输出格式转换
│   ├── batch_synthesize.py                  # 并行批处理
│   ├── dataset_adapter.py                   # 数据集适配器
│   └── evolve_cockpit_skill.py              # 技能进化
├── skills/
│   ├── car-orbit-synthesis/                 # [NEW] ORBIT 流水线技能
│   │   └── SKILL.md
│   ├── cockpit-utterance-synthesis/
│   │   └── SKILL.md
│   ├── cockpit-utterance-validation/
│   │   └── SKILL.md
│   └── cockpit-delegation-orchestrator/
│       └── SKILL.md
├── tools/
│   ├── orbit_seed_tool.py                   # [NEW] ORBIT 种子工具
│   ├── orbit_generalize_tool.py             # [NEW] ORBIT 泛化工具
│   ├── orbit_verify_tool.py                 # [NEW] ORBIT 验证工具
│   ├── orbit_toolset_adapter.py             # [NEW] ORBIT 工具集注册
│   ├── cockpit_synthesis_tool.py            # 核心合成工具
│   ├── delegate_synthesis.py                # 委托合成工具
│   └── toolset_adapter.py                   # 工具集适配器
├── tests/
│   ├── test_orbit_core.py                   # [NEW] ORBIT 纯逻辑测试（30 个）
│   ├── test_orbit_llm_mock.py               # [NEW] ORBIT Mock 测试（46 个）
│   └── test_tools.py                        # 现有工具测试
├── docs/
│   └── orbit-integration-analysis.md        # ORBIT 集成分析
├── PRODUCT_SPEC.md                          # [NEW] 产品规格说明
├── ARCHITECTURE.md                          # [NEW] 架构设计文档
├── INTERFACE_DESIGN.md                      # [NEW] 接口设计文档
├── TESTING.md                               # [NEW] 测试文档
├── REQUIREMENTS_REFLECTION.md               # [NEW] 需求反思文档
├── CLAUDE.md                                # [NEW] AI 架构指南
├── pyproject.toml
├── .gitignore
└── README.md
```

## 测试

```bash
# 运行所有 ORBIT 测试（76 个测试，94% 覆盖率）
python3 -m pytest tests/test_orbit_core.py tests/test_orbit_llm_mock.py -v

# 覆盖率报告
python3 -m pytest tests/test_orbit_core.py tests/test_orbit_llm_mock.py --cov=core --cov-report=term-missing

# 运行所有非集成测试（不需要 API key）
python -m pytest tests/ -v -m "not integration"

# 运行全部测试（需要 OPENAI_API_KEY）
python -m pytest tests/ -v
```

## 版本历史

### v0.3.0 (当前)
- **Car-ORBIT-Agent**：借鉴 ORBIT 框架，实现系统化种子→多维度泛化→级联验证流水线
- **核心引擎层**：新增 `core/` 目录，包含 10 个独立模块
- **种子引擎**：从 YAML/Excel 功能树系统化生成功能种子
- **多维度泛化**：沿口语化、句式变换、参数变化、简化省略、驾驶场景 5 个维度生成变体
- **级联验证**：规则验证→语义验证→安全验证三层流水线，采用短路策略
- **来源链追踪**：完整的来源链和验证链记录，支持 JSONL 轨迹文件
- **ORBIT CLI 命令**：新增 `orbit` 子命令
- **ORBIT 工具集**：3 个 Hermes 工具 + 工具集适配器
- **ORBIT 技能**：`car-orbit-synthesis` SKILL.md
- **76 个测试**：核心模块覆盖率 94%
- **完整文档**：PRODUCT_SPEC、ARCHITECTURE、INTERFACE_DESIGN、TESTING、CLAUDE.md

### v0.2.0
- **并行批处理**：集成 hermes-agent `BatchRunner`，支持多线程并行处理 + 增量断点续传
- **Agent 级验证闭环**：集成 hermes-agent `delegate_task`，通过子代理委托实现 generate → validate → retry 循环
- **数据集适配器**：Excel → JSONL 转换，兼容 batch_runner 输入格式
- **委托编排技能**：新增 `cockpit-delegation-orchestrator` SKILL.md
- **委托合成工具**：新增 `cockpit_delegate_synthesize` 工具
- **工具集适配器**：新增 `toolset_adapter.py`，自动注册到 hermes-agent 工具集
- **26 项单元测试**：覆盖所有新模块

### v0.1.0
- 基础技能系统（synthesis + validation SKILL.md）
- 工具注册（ToolRegistry 模式）
- Standalone / Agent 双模式
- 自我进化集成（GEPA）

## 致谢

- [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) — Agent 核心框架
- [NousResearch/hermes-agent-self-evolution](https://github.com/NousResearch/hermes-agent-self-evolution) — 自我进化优化
- [cockpit-data-synthesis](https://github.com/yangli0403/cockpit-data-synthesis) — 原始项目
- [ORBIT](https://arxiv.org/abs/2501.xxxxx) — 数据合成框架方法论

## License

MIT

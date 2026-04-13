# Hermes Data Agent

> 基于 [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) 构建的座舱 AI 语音助手话术泛化数据合成系统。

本项目是 [cockpit-data-synthesis](https://github.com/yangli0403/cockpit-data-synthesis) 的 Agent 化升级版本，通过复用 Hermes Agent 生态的核心能力（技能系统、工具注册、子代理委托、批量处理、自我进化），将原有的 Python 脚本提升为一个可扩展的 Agent 驱动数据合成平台。

## 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                    Hermes Data Agent v0.2.0                      │
│                                                                 │
│  ┌──────────┐   ┌──────────────┐   ┌────────────────────────┐  │
│  │ CLI 入口  │──▶│ 模式选择器    │──▶│ Standalone / Agent /   │  │
│  │ (click)  │   │              │   │ Delegate / Batch       │  │
│  └──────────┘   └──────────────┘   └────────────────────────┘  │
│                                            │                    │
│         ┌──────────────────────────────────┼──────────┐        │
│         ▼                                  ▼          ▼        │
│  ┌─────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
│  │ 自定义工具   │  │ hermes-agent     │  │ hermes-agent     │  │
│  │ (ToolRegistry│  │ BatchRunner      │  │ delegate_task    │  │
│  │  注册模式)   │  │ (并行+断点续传)  │  │ (子代理验证闭环) │  │
│  └─────────────┘  └──────────────────┘  └──────────────────┘  │
│         │                  │                      │            │
│         ▼                  ▼                      ▼            │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │              SKILL.md 技能文件 (Hermes 格式)              │  │
│  │  • cockpit-utterance-synthesis   (泛化技能)              │  │
│  │  • cockpit-utterance-validation  (验证技能)              │  │
│  │  • cockpit-delegation-orchestrator (委托编排技能) [NEW]   │  │
│  └─────────────────────────────────────────────────────────┘  │
│                           │                                    │
│                           ▼                                    │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │         hermes-agent-self-evolution (GEPA)               │  │
│  │         Prompt 自我进化优化                               │  │
│  └─────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Hermes 生态复用矩阵

| 本项目组件 | 复用来源 | 复用方式 |
|---|---|---|
| `skills/*.md` | hermes-agent SKILL.md 格式 | 技能文件格式 + `skill_utils.py` 加载 |
| `tools/cockpit_synthesis_tool.py` | hermes-agent `ToolRegistry.register()` | 工具注册模式 |
| `tools/delegate_synthesis.py` **[NEW]** | hermes-agent `delegate_task()` | 子代理委托 API |
| `tools/toolset_adapter.py` **[NEW]** | hermes-agent `toolsets.py` | 工具集注册 |
| `scripts/batch_synthesize.py` **[NEW]** | hermes-agent `BatchRunner` | 并行批处理引擎 |
| `scripts/dataset_adapter.py` **[NEW]** | hermes-agent batch JSONL 格式 | 数据集格式适配 |
| `scripts/evolve_cockpit_skill.py` | hermes-agent-self-evolution `evolve()` | GEPA 进化流程 |
| `scripts/cli.py` (`--use-agent`) | hermes-agent `AIAgent` | 对话循环引擎 |

## 四种执行模式

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

### 3. Delegate 模式 (v0.2.0 NEW)
通过 hermes-agent 的 `delegate_task` 派生子 Agent 进行验证闭环。
```bash
python scripts/cli.py synthesize --use-delegate -i data/数据处理测试.xlsx -n 5
```

验证闭环流程：
```
Parent Agent
  ├── delegate_task → Child Agent (Synthesis) → cockpit_synthesize → variants
  ├── delegate_task → Child Agent (Validation) → cockpit_validate → verdict
  └── If failed → delegate_task → Child Agent (Re-synthesis with feedback) → improved variants
      (最多重试 3 次)
```

### 4. Batch 模式 (v0.2.0 NEW)
通过 hermes-agent 的 `BatchRunner` 实现并行处理 + 断点续传。
```bash
# 启动批处理
python scripts/cli.py batch -i data/数据处理测试.xlsx -r my_run -w 4 -b 5

# 中断后恢复
python scripts/cli.py batch -i data/数据处理测试.xlsx -r my_run --resume
```

Batch 模式工作流：
```
Excel → [dataset_adapter] → JSONL → [BatchRunner/ThreadPool] → 并行处理
                                          │
                                    checkpoint.json (增量保存)
                                          │
                                    JSON + Excel 输出
```

## 快速开始

### 安装

```bash
# 基础安装（standalone 模式，无需 hermes-agent）
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

# 并行批处理（4 workers）
python scripts/cli.py batch -i data/数据处理测试.xlsx -r my_run -w 4

# 带子代理验证闭环
python scripts/cli.py synthesize --use-delegate -i data/数据处理测试.xlsx -n 5

# 跳过验证
python scripts/cli.py synthesize -i data/数据处理测试.xlsx --no-validate

# 进化优化 SKILL.md
python scripts/cli.py evolve --skill cockpit-utterance-synthesis --iterations 10
```

### 在 hermes-agent 中使用

当 hermes-agent 已安装时，本项目的工具会自动注册到其 ToolRegistry 中：

```bash
# 启动 hermes-agent 并加载座舱技能
hermes-agent --toolsets cockpit-data --skills cockpit-utterance-synthesis

# 或在 hermes-agent 的交互模式中
hermes --skills cockpit-utterance-synthesis,cockpit-utterance-validation
```

## 项目结构

```
Hermes-data-agent/
├── configs/
│   ├── default.yaml                     # 默认配置（含 batch/delegation 配置）
│   └── batch_config.jsonl               # batch_runner 示例配置
├── data/
│   └── 数据处理测试.xlsx                 # 测试数据
├── datasets/                            # 进化评估数据集
├── output/                              # 输出结果
├── scripts/
│   ├── cli.py                           # 主 CLI 入口（4种模式）
│   ├── batch_synthesize.py              # [NEW] 并行批处理（复用 BatchRunner）
│   ├── dataset_adapter.py              # [NEW] Excel → JSONL 适配器
│   └── evolve_cockpit_skill.py          # 技能进化（复用 self-evolution）
├── skills/
│   ├── cockpit-utterance-synthesis/
│   │   └── SKILL.md                     # 泛化技能（Hermes 格式）
│   ├── cockpit-utterance-validation/
│   │   └── SKILL.md                     # 验证技能（Hermes 格式）
│   └── cockpit-delegation-orchestrator/
│       └── SKILL.md                     # [NEW] 委托编排技能
├── tools/
│   ├── cockpit_synthesis_tool.py        # 核心工具（ToolRegistry 注册）
│   ├── delegate_synthesis.py            # [NEW] 委托合成工具（复用 delegate_task）
│   └── toolset_adapter.py              # [NEW] 工具集注册适配器
├── tests/
│   └── test_tools.py                    # 26 项单元测试
├── pyproject.toml
├── .gitignore
└── README.md
```

## 测试

```bash
# 运行所有非集成测试（不需要 API key）
python -m pytest tests/ -v -m "not integration"

# 运行全部测试（需要 OPENAI_API_KEY）
python -m pytest tests/ -v
```

## 版本历史

### v0.2.0 (当前)
- **并行批处理**：集成 hermes-agent `BatchRunner`，支持多线程并行处理 + 增量断点续传
- **Agent 级验证闭环**：集成 hermes-agent `delegate_task`，通过子代理委托实现 generate → validate → retry 循环
- **数据集适配器**：Excel → JSONL 转换，兼容 batch_runner 输入格式
- **委托编排技能**：新增 `cockpit-delegation-orchestrator` SKILL.md
- **委托合成工具**：新增 `cockpit_delegate_synthesize` 工具
- **工具集适配器**：新增 `toolset_adapter.py`，自动注册到 hermes-agent 工具集
- **26 项单元测试**：覆盖所有新模块（技能加载、Schema 验证、数据适配、变体提取、断点逻辑、编排 Prompt）

### v0.1.0
- 基础技能系统（synthesis + validation SKILL.md）
- 工具注册（ToolRegistry 模式）
- Standalone / Agent 双模式
- 自我进化集成（GEPA）

## 致谢

- [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) — Agent 核心框架
- [NousResearch/hermes-agent-self-evolution](https://github.com/NousResearch/hermes-agent-self-evolution) — 自我进化优化
- [cockpit-data-synthesis](https://github.com/yangli0403/cockpit-data-synthesis) — 原始项目

## License

MIT

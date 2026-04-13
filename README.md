# Hermes Data Agent

基于 [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) 技能系统和 [hermes-agent-self-evolution](https://github.com/NousResearch/hermes-agent-self-evolution) 自我进化能力的座舱 AI 话术数据合成平台。

本项目是 [cockpit-data-synthesis](https://github.com/yangli0403/cockpit-data-synthesis) 的 Agent 化升级版，将原有的脚本式泛化流程重构为 Hermes Agent 驱动的技能系统，实现了更高质量的数据合成和自动化的 Prompt 进化优化。

## 架构概览

```
┌─────────────────────────────────────────────────────────┐
│                    Hermes Data Agent                     │
├─────────────────────────────────────────────────────────┤
│  CLI (scripts/cli.py)                                    │
│    ├── synthesize  →  批量话术泛化合成                     │
│    ├── evolve      →  SKILL.md 自我进化优化               │
│    └── info        →  系统信息和集成状态                   │
├─────────────────────────────────────────────────────────┤
│  Skills (skills/)                    ← hermes-agent 格式  │
│    ├── cockpit-utterance-synthesis/SKILL.md               │
│    └── cockpit-utterance-validation/SKILL.md              │
├─────────────────────────────────────────────────────────┤
│  Tools (tools/)                      ← hermes-agent 注册  │
│    └── cockpit_synthesis_tool.py                          │
│        ├── cockpit_synthesize        (单条泛化)           │
│        ├── cockpit_validate          (质量验证)           │
│        └── cockpit_batch_synthesize  (批量处理)           │
├─────────────────────────────────────────────────────────┤
│  Evolution (scripts/evolve_cockpit_skill.py)              │
│    └── 复用 hermes-agent-self-evolution 的 GEPA 流程       │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────────────┐  ┌──────────────────────────┐  │
│  │   hermes-agent      │  │ hermes-agent-self-       │  │
│  │   (核心依赖)         │  │ evolution (进化依赖)      │  │
│  │   • AIAgent         │  │ • DSPy + GEPA            │  │
│  │   • ToolRegistry    │  │ • SkillModule            │  │
│  │   • batch_runner    │  │ • LLMJudge               │  │
│  │   • skill_utils     │  │ • ConstraintValidator    │  │
│  └─────────────────────┘  └──────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## 与 Hermes Agent 的集成关系

本项目**不是**重新实现 Hermes Agent 的功能，而是作为其**技能插件**和**工具扩展**运行。具体复用关系如下：

| 组件 | 来源 | 复用方式 |
|------|------|----------|
| 技能格式 (SKILL.md) | hermes-agent | 遵循其 YAML frontmatter + Markdown body 格式 |
| 工具注册 (ToolRegistry) | hermes-agent/tools/registry.py | 自定义工具通过 `registry.register()` 注册 |
| Agent 引擎 (AIAgent) | hermes-agent/run_agent.py | `--use-agent` 模式下驱动完整对话循环 |
| 批量处理 (batch_runner) | hermes-agent/batch_runner.py | 并行批处理、检查点、轨迹保存 |
| 技能进化 (GEPA) | hermes-agent-self-evolution | `evolve` 命令直接调用其优化流程 |
| 评估数据集 | hermes-agent-self-evolution | 复用 EvalDataset / SyntheticDatasetBuilder |
| 适应度评估 | hermes-agent-self-evolution | 复用 LLMJudge + skill_fitness_metric |
| 约束验证 | hermes-agent-self-evolution | 复用 ConstraintValidator |

## 快速开始

### 安装

```bash
# 基础安装（standalone 模式，无需 hermes-agent）
pip install openpyxl pandas click rich pyyaml openai

# 完整安装（包含 hermes-agent 集成）
pip install -e ".[dev]"
```

### 使用

```bash
# 查看系统信息
python scripts/cli.py info

# 批量合成（standalone 模式）
python scripts/cli.py synthesize \
  -i data/数据处理测试.xlsx \
  -n 5 \
  --limit 10

# 批量合成（hermes-agent 模式）
python scripts/cli.py synthesize \
  -i data/数据处理测试.xlsx \
  --use-agent \
  -n 5

# 跳过验证
python scripts/cli.py synthesize \
  -i data/数据处理测试.xlsx \
  --no-validate

# 进化优化 SKILL.md（需要 hermes-agent-self-evolution）
python scripts/cli.py evolve \
  --skill cockpit-utterance-synthesis \
  --iterations 10

# 或直接运行进化脚本
python scripts/evolve_cockpit_skill.py \
  --skill cockpit-utterance-synthesis \
  --eval-source golden \
  --input-excel data/数据处理测试.xlsx
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
├── skills/                              # Hermes Agent 技能文件
│   ├── cockpit-utterance-synthesis/
│   │   └── SKILL.md                     # 泛化技能指令
│   └── cockpit-utterance-validation/
│       └── SKILL.md                     # 验证技能指令
├── tools/                               # Hermes Agent 自定义工具
│   └── cockpit_synthesis_tool.py        # 泛化/验证/批处理工具
├── scripts/                             # CLI 和辅助脚本
│   ├── cli.py                           # 主 CLI 入口
│   └── evolve_cockpit_skill.py          # 进化脚本
├── configs/                             # 配置文件
│   ├── default.yaml                     # 默认配置
│   └── batch_config.jsonl               # batch_runner 配置
├── data/                                # 输入数据
│   └── 数据处理测试.xlsx
├── datasets/                            # 进化评估数据集
├── output/                              # 输出结果
├── tests/                               # 测试
├── pyproject.toml                       # 项目配置
└── README.md
```

## 双模式运行

本项目支持两种运行模式：

**Standalone 模式**：不依赖 hermes-agent 安装，直接调用工具处理函数。适合快速使用和轻量级部署。

**Agent 模式**：通过 hermes-agent 的 AIAgent 驱动完整的对话循环，支持工具调用、错误恢复、上下文管理和子代理委托。适合复杂场景和需要 Agent 自主决策的任务。

## 自我进化

通过 `evolve` 命令，可以使用 hermes-agent-self-evolution 的 GEPA（Genetic-Pareto Prompt Evolution）算法自动优化 SKILL.md 文件。进化流程：

1. 加载目标 SKILL.md
2. 生成或加载评估数据集
3. 使用 DSPy 将 SKILL.md 包装为可优化参数
4. 运行 GEPA 优化器（变异 → 评估 → 选择）
5. 验证进化后的 SKILL.md 满足约束条件
6. 部署最优版本

## 致谢

- [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) — Agent 核心框架
- [NousResearch/hermes-agent-self-evolution](https://github.com/NousResearch/hermes-agent-self-evolution) — 自我进化优化
- [cockpit-data-synthesis](https://github.com/yangli0403/cockpit-data-synthesis) — 原始项目

## License

MIT

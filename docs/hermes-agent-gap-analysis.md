# Hermes Data Agent 与 Hermes Agent 真实功能差距分析报告

在完成 v0.2.0 版本的迭代后，我重新对 `hermes-agent` 的完整源码（20万行规模）与当前 `Hermes-data-agent`（2500行规模）进行了严格的代码级对照。

本报告旨在诚实地评估当前的复用程度，揭示哪些是真正的功能复用，哪些是"伪复用"（仅借用接口或概念），以及我们距离一个完整的 Hermes 生态 Agent 还有多远。

## 1. 核心架构与代码规模对比

首先，从代码规模上可以看出两者的定位差异：

| 项目 | 代码行数 | 核心模块数 | 工具数量 | 定位 |
|---|---|---|---|---|
| **hermes-agent** | ~205,000 行 | 8 个核心引擎模块 | 50+ 个内置工具 | 通用、多模态、RL 驱动的 Agent 操作系统 |
| **Hermes-data-agent** | ~2,500 行 | 0 个（全依赖外部） | 3 个自定义工具 | 垂直领域的特定任务（数据合成）执行脚本 |

`Hermes-data-agent` 并不是一个独立的 Agent 框架，而是一个**挂载在 Hermes 生态上的特定领域插件集**。

## 2. 真实复用 vs 伪复用分析

通过对 `import` 语句和调用逻辑的追踪，以下是各项功能的真实复用情况：

### 2.1 真实深度复用的功能

这些功能我们确实调用了 `hermes-agent` 的核心引擎，享受了其底层的复杂逻辑：

* **工具注册机制 (`ToolRegistry`)**：我们通过 `registry.register()` 将座舱工具注入了 Hermes 的全局工具表，这使得任何运行在 Hermes 上的 Agent 都能无缝发现和使用这些工具。
* **技能系统格式 (`SKILL.md`)**：我们严格遵循了 Hermes 的 YAML Frontmatter + Markdown 规范，这使得我们的技能可以被 Hermes 的 `skill_utils.py` 原生解析和加载。
* **自我进化管线 (`hermes-agent-self-evolution`)**：我们的 `evolve_cockpit_skill.py` 真实调用了上游的 `evolve()` 函数，完整复用了 DSPy 封装、GEPA 遗传算法和 LLMJudge 评估逻辑。

### 2.2 浅层复用（包装/适配）的功能

这些功能我们虽然使用了 Hermes 的组件，但主要是在外层做了一层包装，并未深入其生态：

* **并行批处理 (`BatchRunner`)**：
  * **现状**：我们编写了 `dataset_adapter.py` 将 Excel 转换为 JSONL，然后调用 `BatchRunner.run()`。
  * **差距**：Hermes 的 `BatchRunner` 实际上是为了生成 RL 训练轨迹（Trajectory）而设计的，它会保存详细的 `trajectory.json`。而我们目前只关心最终的 JSON/Excel 输出，忽略了轨迹数据的高级价值。
* **子代理委托 (`delegate_task`)**：
  * **现状**：我们在 `delegate_synthesis.py` 中调用了 `delegate_task`，实现了 Parent-Child 的验证闭环。
  * **差距**：我们是在**自定义工具内部**硬编码调用 `delegate_task`，而不是让 Agent 引擎自主决定何时委托。这更像是一个"带 LLM 调用的复杂函数"，而不是真正的多智能体协同。

### 2.3 伪复用（仅概念借用）的功能

* **Agent 对话循环 (`AIAgent`)**：
  * **现状**：CLI 中的 `--use-agent` 模式确实实例化了 `AIAgent`。
  * **差距**：我们只是用它来执行单次 Prompt（"请生成话术..."），并没有利用其多轮对话、状态机（`hermes_state.py`）或记忆管理能力。

## 3. 尚未开发的 Hermes 核心能力（主要差距）

`hermes-agent` 作为一个"Agent 操作系统"，其最强大的几个特性在当前项目中完全缺失：

### 3.1 记忆与状态持久化 (Memory & State)
* **Hermes 能力**：拥有完整的 `SessionDB` (SQLite) 和 `memory_tool.py`，支持跨会话的记忆检索、状态恢复和长期知识积累。
* **当前差距**：`Hermes-data-agent` 是无状态的。每次运行都是全新的，Agent 无法记住"上次生成这种参数组合时犯过什么错"。

### 3.2 轨迹压缩与 RL 数据飞轮 (Trajectory & RL)
* **Hermes 能力**：核心模块 `trajectory_compressor.py` 和 `rl_training_tool.py`。Hermes 的终极目标是收集 Agent 的执行轨迹，压缩后用于强化学习（RL）微调模型。
* **当前差距**：我们虽然用了 `BatchRunner`，但完全丢弃了生成的轨迹数据，没有建立"合成数据 -> 评估 -> 轨迹收集 -> 模型微调"的数据飞轮。

### 3.3 复杂环境沙盒 (Environments)
* **Hermes 能力**：支持 Docker, Modal, SSH 等多种隔离环境（`tools/environments/`），用于安全执行代码或浏览器操作。
* **当前差距**：座舱数据合成目前纯依赖 LLM 文本生成，不需要执行代码，因此未使用此功能。但如果未来需要 Agent 自动验证生成的代码或查询外部 API，这将是一个巨大差距。

### 3.4 丰富的多模态工具链 (Tool Ecosystem)
* **Hermes 能力**：内置了浏览器控制（`browser_tool.py`）、终端执行（`terminal_tool.py`）、视觉处理（`vision_tools.py`）等 50+ 工具。
* **当前差距**：我们目前只注册了 3 个纯文本处理工具，没有利用 Hermes 强大的外部世界交互能力（例如：让 Agent 自己去网上搜索最新的座舱话术规范）。

## 4. 总结与演进建议

当前的 `Hermes-data-agent` 成功完成了**第一阶段：从脚本到插件的重构**。它证明了我们可以将特定领域的业务逻辑无缝挂载到 Hermes 生态上。

但要真正发挥 Hermes 的威力，**第二阶段的演进方向**应该是：

1. **接入记忆系统**：让 Agent 在处理批量数据时，能动态总结易错点并写入 Memory，在后续生成中自动规避。
2. **激活 RL 飞轮**：收集 `BatchRunner` 产生的成功与失败轨迹，格式化为 DPO（Direct Preference Optimization）训练数据，用于微调专属的座舱合成小模型。
3. **引入搜索工具**：在 `SKILL.md` 中授权 Agent 使用 Hermes 的 `web_tools`，在遇到不熟悉的"二级功能"时，允许 Agent 先搜索背景知识再进行泛化。

# Car-ORBIT-Agent — 架构设计文档

## 高层架构

![架构图](diagrams/architecture.png)

Car-ORBIT-Agent 采用**六层分层架构**，自顶向下依次为 CLI 入口层、技能层、工具层、核心引擎层、基础设施层和适配器层。该架构的核心设计原则是**与 Hermes-data-agent 现有架构保持一致**——技能定义"做什么"，工具封装"怎么做"，引擎实现"具体逻辑"——同时引入 ORBIT 框架的级联验证和来源链追踪能力。

## 模块职责

| 模块 | 主要职责 | 技术选型 | 依赖关系 |
|------|----------|----------|----------|
| **CLI 入口** (`scripts/cli.py` — `orbit` 子命令) | 解析命令行参数，编排完整的 ORBIT 流水线执行，输出统计摘要 | Click + Rich | 技能层、核心引擎层 |
| **技能定义** (`skills/car-orbit-synthesis/SKILL.md`) | 为 Hermes Agent 提供 ORBIT 流水线的执行指南，定义数据格式、维度规则和验证标准 | Markdown (YAML front matter) | 无 |
| **种子工具** (`tools/orbit_seed_tool.py`) | 封装种子生成能力为 Hermes 可调用的工具函数，处理参数校验和错误包装 | Python | SeedEngine |
| **泛化工具** (`tools/orbit_generalize_tool.py`) | 封装多维度泛化能力为 Hermes 可调用的工具函数 | Python | GeneralizationEngine |
| **验证工具** (`tools/orbit_verify_tool.py`) | 封装级联验证能力为 Hermes 可调用的工具函数 | Python | CascadeOrchestrator |
| **SeedEngine** (`core/seed_engine.py`) | 解析功能树 YAML/JSON 配置，从 Excel 提取种子，执行组合策略生成种子列表 | PyYAML, pandas, openpyxl | ConfigLoader |
| **GeneralizationEngine** (`core/generalization_engine.py`) | 构建多维度泛化 Prompt，调用 LLM 生成变体，管理维度配置 | Python | LLMClient, ProvenanceTracker |
| **RuleVerifier** (`core/rule_verifier.py`) | 基于纯 Python 逻辑执行参数完整性、长度约束、车辆约束规则验证 | Python | 无外部依赖 |
| **SemanticVerifier** (`core/semantic_verifier.py`) | 调用 LLM 判断变体与原始话术的语义一致性和自然度 | Python | LLMClient |
| **SafetyVerifier** (`core/safety_verifier.py`) | 调用 LLM 检查变体是否存在驾驶安全风险 | Python | LLMClient |
| **CascadeOrchestrator** (`core/cascade_orchestrator.py`) | 编排三层级联验证流水线，汇总置信度分数，管理验证链记录 | Python | RuleVerifier, SemanticVerifier, SafetyVerifier, ProvenanceTracker |
| **LLMClient** (`core/llm_client.py`) | 封装 OpenAI 兼容 API 调用，提供重试、回退、模型选择能力 | openai | 无 |
| **ProvenanceTracker** (`core/provenance_tracker.py`) | 记录来源链和验证链，持久化为 JSONL 轨迹文件 | Python (json) | 无 |
| **ConfigLoader** (`core/config_loader.py`) | 加载和合并 YAML 配置文件（default.yaml + 用户覆盖） | PyYAML | 无 |
| **toolset_adapter** (`tools/orbit_toolset_adapter.py`) | 将 car-orbit 工具集注册到 Hermes Agent 的 TOOLSETS 注册表 | Python | hermes-agent (可选) |
| **orbit_dataset_adapter** (`scripts/orbit_dataset_adapter.py`) | 将流水线输出转换为 JSON、JSONL、Excel 等格式，生成统计摘要 | pandas, openpyxl, json | 无 |

## 目录结构

```
Hermes-data-agent/
├── core/                                  # 新增：核心引擎层
│   ├── __init__.py
│   ├── seed_engine.py                     # 种子生成引擎
│   ├── generalization_engine.py           # 多维度泛化引擎
│   ├── rule_verifier.py                   # 规则验证器
│   ├── semantic_verifier.py               # 语义验证器
│   ├── safety_verifier.py                 # 安全验证器
│   ├── cascade_orchestrator.py            # 级联验证编排器
│   ├── llm_client.py                      # LLM 客户端
│   ├── provenance_tracker.py              # 来源链/验证链追踪器
│   └── config_loader.py                   # 配置加载器
├── tools/
│   ├── cockpit_synthesis_tool.py          # 现有
│   ├── delegate_synthesis.py              # 现有
│   ├── pre_router_synthesis_tool.py       # 现有
│   ├── toolset_adapter.py                 # 现有
│   ├── orbit_seed_tool.py                 # 新增：种子生成工具
│   ├── orbit_generalize_tool.py           # 新增：泛化工具
│   ├── orbit_verify_tool.py              # 新增：验证工具
│   └── orbit_toolset_adapter.py           # 新增：工具集注册
├── skills/
│   ├── cockpit-utterance-synthesis/       # 现有
│   ├── pre-router-synthesis/              # 现有
│   └── car-orbit-synthesis/               # 新增
│       └── SKILL.md
├── scripts/
│   ├── cli.py                             # 现有（新增 orbit 子命令）
│   ├── batch_synthesize.py                # 现有
│   ├── dataset_adapter.py                 # 现有
│   └── orbit_dataset_adapter.py           # 新增：输出格式转换
├── configs/
│   ├── default.yaml                       # 现有（新增 orbit 配置段）
│   └── orbit_vehicle_tree_sample.yaml     # 新增：示例功能树配置
├── data/
│   └── orbit_seeds_sample.yaml            # 新增：示例种子文件
├── tests/
│   ├── test_tools.py                      # 现有
│   ├── test_orbit_seed_engine.py          # 新增
│   ├── test_orbit_generalization.py       # 新增
│   ├── test_orbit_verification.py         # 新增
│   └── test_orbit_integration.py          # 新增
└── output/
    └── orbit/                             # 新增：ORBIT 输出目录
```

## 数据流场景

### 场景 1：完整 ORBIT 流水线执行（写操作）

本场景描述用户通过 CLI 执行完整的 ORBIT 流水线，从功能树配置生成最终的训练数据集。

1. **入口**：用户执行 `hermes-data orbit --input configs/orbit_vehicle_tree_sample.yaml --output output/orbit/ --num-variants 5`。CLI 入口层解析参数，加载 `car-orbit-synthesis` 技能定义以获取维度规则和验证标准。

2. **种子生成**：CLI 调用 `SeedEngine.generate_from_config(config_path)`。SeedEngine 通过 `ConfigLoader` 加载功能树 YAML 配置，解析领域、功能、参数定义，然后执行组合策略（笛卡尔积 + 采样）生成种子列表。每个种子是一个 `Seed` 数据对象，包含 `domain`、`function`、`params`、`standard_utterance` 字段。`ProvenanceTracker` 记录每个种子的来源信息。

3. **多维度泛化**：CLI 遍历种子列表（支持 `--limit` 截断），对每个种子调用 `GeneralizationEngine.generalize(seed, num_variants, dimensions)`。引擎根据维度配置构建 Prompt，通过 `LLMClient` 调用 LLM API 生成变体。LLMClient 内置重试机制（最多 3 次，指数退避），批量失败时回退到单条处理。`ProvenanceTracker` 记录每个变体的生成策略和维度信息。

4. **级联验证**：对每个种子的变体列表，CLI 调用 `CascadeOrchestrator.verify(variants, seed)`。编排器依次执行三层验证：（a）`RuleVerifier` 执行纯 Python 规则检查——参数完整性、长度约束（5-50 字符）、车辆约束规则（如行驶中禁止视频播放），未通过的变体立即标记为失败且不进入下一层；（b）`SemanticVerifier` 通过 `LLMClient` 调用 LLM 评判语义一致性和自然度，返回 0.0-1.0 的分数，低于阈值（默认 0.7）的变体标记为失败；（c）`SafetyVerifier` 通过 `LLMClient` 调用 LLM 检查驾驶安全风险。每层验证结果由 `ProvenanceTracker` 记录到验证链中。最终，编排器汇总三层分数为综合置信度。

5. **输出**：CLI 调用 `orbit_dataset_adapter` 将通过验证的变体（含来源链和验证链）转换为 JSON/JSONL 和 Excel 格式，写入 `output/orbit/` 目录。同时在终端通过 Rich 输出统计摘要：总种子数、总变体数、各层验证通过率、平均置信度。

### 场景 2：从 Excel 提取种子并泛化（读 + 写混合操作）

本场景描述用户使用现有的 Excel 数据文件作为种子来源，跳过功能树组合步骤。

1. **入口**：用户执行 `hermes-data orbit --input data/数据处理测试.xlsx --output output/orbit/ --num-variants 3`。CLI 检测到输入文件为 `.xlsx` 格式，切换到 Excel 提取模式。

2. **种子提取**：CLI 调用 `SeedEngine.extract_from_excel(excel_path)`。SeedEngine 使用 pandas 读取 Excel 文件，将每行数据映射为 `Seed` 对象。映射规则：`一级分类` → `domain`，`二级分类` → `function`，`标准话术` → `standard_utterance`，`参数` 列（如有）→ `params`。对于缺少必要列的 Excel 文件，抛出 `ValueError` 并提示缺少的列名。

3. **泛化与验证**：后续流程与场景 1 的步骤 3-5 完全一致。

### 场景 3：单条种子的交互式处理

本场景描述开发者在调试时对单条种子执行完整流水线。

1. **入口**：开发者在 Python 脚本或 REPL 中直接调用工具函数 `handle_orbit_seed_generate({"config_path": "...", "limit": 1})`。

2. **处理**：工具函数内部调用 `SeedEngine` 生成 1 个种子，然后调用 `GeneralizationEngine` 泛化，最后调用 `CascadeOrchestrator` 验证。

3. **输出**：返回包含完整来源链和验证链的 JSON 对象，开发者可直接检查每个字段。

## 核心数据结构

### Seed（种子）

```python
@dataclass
class Seed:
    seed_id: str              # 唯一标识，如 "music_play_001"
    domain: str               # 领域，如 "音乐"
    function: str             # 功能，如 "播放音乐"
    sub_function: str         # 子功能，如 "按歌手名播放"
    standard_utterance: str   # 标准话术，如 "播放周杰伦的音乐"
    params: Dict[str, str]    # 参数，如 {"歌手名": "周杰伦"}
    source_type: str          # 来源类型："config" 或 "excel"
```

### GeneralizationResult（泛化结果）

```python
@dataclass
class GeneralizationResult:
    seed: Seed
    variants: List[str]                    # 生成的变体列表
    generation_strategies: List[str]       # 每个变体的生成策略
    dimensions_used: List[str]             # 使用的维度
    llm_model: str                         # 使用的 LLM 模型
    timestamp: str                         # 生成时间
```

### VerificationResult（验证结果）

```python
@dataclass
class VerificationResult:
    variant: str
    rule_check: StageResult       # 规则验证结果
    semantic_check: StageResult   # 语义验证结果
    safety_check: StageResult     # 安全验证结果
    overall_passed: bool          # 综合是否通过
    confidence_score: float       # 综合置信度 (0.0-1.0)

@dataclass
class StageResult:
    stage: str          # "rule" | "semantic" | "safety"
    passed: bool
    score: float        # 0.0-1.0
    reason: str         # 通过/失败原因
```

### OrbitRecord（最终输出记录）

```python
@dataclass
class OrbitRecord:
    record_id: str
    standard_utterance: str
    variant: str
    source_chain: Dict          # 来源链
    verification_chain: List    # 验证链
    confidence_score: float
    label_quality: str          # "synthetic_verified"
```

## 设计决策

### 决策 1：新建 `core/` 目录而非扩展现有 `tools/`

- **背景**：car-orbit-agent 的核心逻辑（种子引擎、泛化引擎、三个验证器、级联编排器）比现有的单文件工具（如 `cockpit_synthesis_tool.py`）复杂得多，需要更清晰的模块划分。
- **备选方案**：（A）将所有逻辑放在一个 `tools/orbit_synthesis_tool.py` 中，类似现有的 `pre_router_synthesis_tool.py`；（B）新建 `core/` 目录，将引擎逻辑与工具层分离。
- **最终决策**：选择方案 B，新建 `core/` 目录。
- **理由**：方案 A 会导致单文件过于庞大（预计 1500+ 行），难以测试和维护。`core/` 目录中的每个模块职责单一，可以独立测试，也便于未来其他 Agent 复用（如 `LLMClient` 和 `ProvenanceTracker`）。工具层（`tools/`）仅作为 Hermes 生态的薄封装层，调用 `core/` 中的引擎。

### 决策 2：级联验证采用"短路"策略而非"全量"策略

- **背景**：三层验证（规则→语义→安全）可以采用两种策略：（A）全量执行所有三层，最后汇总；（B）短路执行，某层失败则跳过后续层。
- **备选方案**：方案 A（全量）可以提供更完整的诊断信息；方案 B（短路）可以节省 LLM API 调用成本。
- **最终决策**：选择方案 B（短路策略），但在验证链中记录"跳过"状态。
- **理由**：规则验证是纯 Python 逻辑（零成本），如果规则验证都未通过（如参数缺失），则没有必要再调用 LLM 进行语义和安全验证。这可以显著降低 API 调用成本。同时，验证链中记录 `skipped` 状态，确保可追溯性不受影响。

### 决策 3：LLMClient 独立封装而非直接使用 openai 库

- **背景**：现有代码中 LLM 调用散布在各个工具文件中（如 `cockpit_synthesis_tool.py` 的 `_get_client()`），缺乏统一的重试和回退逻辑。
- **备选方案**：（A）继续在每个工具中直接调用 openai 库；（B）抽取统一的 `LLMClient`。
- **最终决策**：选择方案 B，创建 `core/llm_client.py`。
- **理由**：统一的 LLMClient 可以集中管理重试策略（指数退避）、模型选择（不同验证阶段使用不同模型）、API 密钥配置和调用计数。这也为未来接入其他 LLM 提供商（如本地模型）提供了扩展点。

### 决策 4：配置段嵌入现有 `default.yaml` 而非独立配置文件

- **背景**：car-orbit-agent 需要配置项（模型选择、维度参数、验证阈值等），需要决定配置文件的组织方式。
- **备选方案**：（A）创建独立的 `configs/orbit.yaml`；（B）在现有 `configs/default.yaml` 中新增 `orbit:` 配置段。
- **最终决策**：选择方案 B，嵌入现有配置文件。
- **理由**：与现有的 `cockpit:` 和 `pre_router:` 配置段保持一致的组织方式。用户只需维护一个配置文件。同时提供 `configs/orbit_vehicle_tree_sample.yaml` 作为功能树配置的示例文件（这是输入数据，不是系统配置）。

## 可扩展性考虑

本架构在以下维度支持扩展：

**新增验证层**：`CascadeOrchestrator` 采用列表驱动的验证器注册机制。新增验证层只需实现 `BaseVerifier` 接口（包含 `verify(variant, seed) -> StageResult` 方法），然后在配置中注册即可。例如，未来可以新增"方言验证器"或"多语言验证器"。

**新增泛化维度**：`GeneralizationEngine` 的维度配置是数据驱动的（YAML 配置）。新增维度只需在配置中定义维度名称和对应的 Prompt 片段，无需修改引擎代码。

**新增数据源**：`SeedEngine` 通过策略模式支持多种数据源。当前支持 YAML 配置和 Excel 文件，未来可以新增 JSON、CSV、数据库等数据源，只需实现对应的 `SeedSource` 策略。

**批量处理**：当 hermes-agent 可用时，CLI 层可以将种子列表分发给 `BatchRunner` 进行并行处理，每个 worker 独立执行泛化和验证流水线。这不需要修改核心引擎层的代码。

## 安全性考虑

**API 密钥保护**：LLM API 密钥通过环境变量（`OPENAI_API_KEY`）注入，不存储在配置文件或代码中。`ConfigLoader` 在加载配置时会检查环境变量是否已设置。

**输入验证**：`SeedEngine` 对所有输入配置进行严格的 schema 验证（必要字段检查、类型检查），防止恶意或格式错误的配置导致异常。

**安全验证层**：`SafetyVerifier` 作为最后一道防线，确保生成的话术变体不包含可能导致驾驶安全风险的内容。这是车载场景特有的安全需求，也是本架构区别于通用数据合成框架的关键特性。

**输出隔离**：所有输出文件写入 `output/orbit/` 子目录，不会覆盖现有的 cockpit 或 pre-router 输出。

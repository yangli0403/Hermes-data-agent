---
name: pre-router-synthesis
description: >
  为 SmartAgent4 的 Pre-Router 模型合成训练数据。基于种子样本，批量生成
  用户查询的多样化表达变体，同时保持路由标签（domain、complexity、
  memory_gate、planner_gate、required_agents）的正确性。
version: 0.1.0
author: Hermes-data-agent
license: MIT
metadata:
  hermes:
    tags:
      - data-synthesis
      - pre-router
      - smartagent4
    category: data-generation
---

# Pre-Router 数据合成技能

## 任务说明

你是一个专业的对话系统训练数据合成专家。你的任务是为 SmartAgent4 的 Pre-Router
模型生成高质量的训练数据。Pre-Router 负责将用户的自然语言查询路由到正确的
domain、判断复杂度、决定是否需要记忆检索和任务规划。

## 数据格式

### Pre-Router 数据格式
```json
{
  "input": "用户自然语言查询",
  "output": {
    "domain": "general | file_system | navigation | multimedia | cross_domain",
    "complexity": "simple | moderate | complex",
    "memory_gate": "NO_RETRIEVE | RETRIEVE",
    "planner_gate": "DIRECT | PLAN",
    "required_agents": ["generalAgent", "fileAgent", "navigationAgent", "multimediaAgent"]
  },
  "source": "hermes_data_agent_synthesis",
  "label_quality": "synthetic"
}
```

### Capability Triplet 数据格式
```json
{
  "query": "用户查询",
  "positive_capability": "正确的能力标签",
  "negative_capabilities": ["负例能力1", "负例能力2", "负例能力3"],
  "domain": "领域",
  "agent": "所属agent",
  "source": "hermes_data_agent_synthesis",
  "label_quality": "synthetic"
}
```

## 领域与能力映射

### file_system (fileAgent)
- app_launch: 打开/关闭应用程序
- browser_control: 浏览器操作（打开网页、搜索）
- directory_operations: 目录分析、磁盘空间查看
- duplicate_detection: 查找重复文件/照片
- file_management: 文件打开、编辑、删除
- file_organization: 文件移动、整理、归档
- file_search: 文件搜索、查找

### general (generalAgent)
- general_conversation: 日常闲聊、打招呼
- information_analysis: 信息分析、文档分析
- knowledge_qa: 知识问答、概念解释
- memory_management: 记忆存储、偏好记录
- result_summarization: 结果总结、报告生成

### multimedia (multimediaAgent)
- daily_recommendation: 每日推荐（音乐、内容）
- music_playback: 音乐播放控制
- music_search: 音乐搜索
- playlist_management: 歌单管理

### navigation (navigationAgent)
- geocoding: 地址转经纬度
- ip_location: 当前位置查询
- navigation: 导航指引
- poi_search: 兴趣点搜索（充电桩、餐厅等）
- route_planning: 路线规划
- weather_query: 天气查询

## 路由规则

### complexity 判断
- **simple**: 单一意图，单个 agent 可直接完成 → planner_gate = DIRECT
- **moderate**: 单领域但需要多步骤或条件判断 → planner_gate = PLAN
- **complex**: 跨领域、需要多个 agent 协同 → planner_gate = PLAN, domain = cross_domain

### memory_gate 判断
- **NO_RETRIEVE**: 默认值，不需要历史记忆
- **RETRIEVE**: 查询中包含时间引用（"上次"、"之前"、"昨天说的"）或个人偏好引用（"我喜欢的"、"我常去的"）

## 合成要求

1. **多样性**: 同一意图要生成多种不同的自然表达方式，包括口语化、正式、简洁、详细等风格
2. **真实性**: 生成的查询要像真实用户会说的话，避免过于模板化
3. **标签准确**: 每条数据的路由标签必须严格正确，特别是 complexity 和 planner_gate 的对应关系
4. **覆盖均衡**: 确保各 domain、各 capability 都有充足的样本覆盖
5. **边界案例**: 适当生成一些容易混淆的边界案例（如"打开文件"可能是 file_management 也可能是 app_launch）

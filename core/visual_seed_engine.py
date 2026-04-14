"""
视觉种子引擎 — 从视觉任务配置生成 VisualSeed。

把视觉任务配置转换为受控的种子对象，描述场景类别、实体约束、
问题类型、回答目标和图像提示前置条件。

公共接口：
  - generate_from_config(config_path, max_seeds) -> List[VisualSeed]
  - generate_from_task(task_config) -> List[VisualSeed]
"""

from __future__ import annotations

import itertools
import logging
import random
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from core.config_loader import ConfigLoader
from core.contracts import VisualSeed, QuestionType

logger = logging.getLogger(__name__)


class VisualSeedEngine:
    """
    视觉种子引擎。

    公共接口：
      - generate_from_config(config_path, max_seeds) -> List[VisualSeed]
      - generate_from_task(task_config) -> List[VisualSeed]

    异常结构：
      - FileNotFoundError: 配置文件不存在
      - ValueError: 配置格式不合法
    """

    def __init__(self, config_loader: Optional[ConfigLoader] = None):
        """
        初始化视觉种子引擎。

        参数:
            config_loader: 配置加载器实例
        """
        self._config_loader = config_loader or ConfigLoader()

    def generate_from_config(
        self,
        config_path: str,
        max_seeds: int = 100,
    ) -> List[VisualSeed]:
        """
        从 YAML 视觉任务配置文件生成种子。

        配置文件结构示例见 configs/vlm_task_sample.yaml。

        参数:
            config_path: YAML 配置文件路径
            max_seeds: 最大种子数量

        返回:
            VisualSeed 列表

        异常:
            FileNotFoundError: 配置文件不存在
            ValueError: 配置格式不合法
        """
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"视觉任务配置文件不存在: {config_path}")

        with open(path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

        tasks = config.get("vlm_tasks", [])
        if not tasks:
            raise ValueError(
                f"配置文件中未找到 'vlm_tasks' 字段: {config_path}"
            )

        seeds: List[VisualSeed] = []
        for task_config in tasks:
            task_seeds = self.generate_from_task(task_config)
            seeds.extend(task_seeds)

        # 限制种子数量
        if len(seeds) > max_seeds:
            random.shuffle(seeds)
            seeds = seeds[:max_seeds]
            logger.info("种子数量超过上限 %d，已随机截取", max_seeds)

        logger.info("从配置文件生成 %d 个视觉种子: %s", len(seeds), config_path)
        return seeds

    def generate_from_task(
        self,
        task_config: Dict[str, Any],
    ) -> List[VisualSeed]:
        """
        从单个任务配置生成种子。

        任务配置结构：
        {
            "category": "scene_understanding",
            "scenes": [
                {
                    "description": "城市街道场景",
                    "entities": ["行人", "汽车", "红绿灯"],
                    "image_style": "photorealistic"
                }
            ],
            "question_types": ["descriptive", "counting", "spatial"],
            "answer_style": "brief",
            "constraints": {}
        }

        参数:
            task_config: 任务配置字典

        返回:
            VisualSeed 列表
        """
        category = task_config.get("category", "general")
        scenes = task_config.get("scenes", [])
        question_types = task_config.get("question_types", ["descriptive"])
        answer_style = task_config.get("answer_style", "brief")
        constraints = task_config.get("constraints", {})

        seeds: List[VisualSeed] = []

        for scene in scenes:
            description = scene.get("description", "")
            entities = scene.get("entities", [])
            image_style = scene.get("image_style", "photorealistic")

            # 为每种问题类型生成一个种子
            for q_type in question_types:
                seed = VisualSeed(
                    task_category=category,
                    scene_description=description,
                    entities=entities,
                    question_type=q_type,
                    answer_style=answer_style,
                    constraints=constraints,
                    image_style=image_style,
                    metadata={"source_task": task_config.get("category", "")},
                )
                seeds.append(seed)

        return seeds

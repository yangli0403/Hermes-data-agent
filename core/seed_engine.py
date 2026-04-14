"""
种子生成引擎 — 从功能树配置或 Excel 文件中系统化生成功能种子。

种子（Seed）是 ORBIT 流水线的起点。每个种子代表一个具体的车载功能 +
参数组合，后续的泛化和验证都围绕种子展开。

支持两种数据源：
  1. YAML/JSON 功能树配置 → 通过组合策略自动生成种子
  2. Excel 文件 → 从现有数据中提取种子
"""

from __future__ import annotations

import itertools
import json
import logging
import random
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import yaml

from core.config_loader import ConfigLoader

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class Seed:
    """功能种子 — ORBIT 流水线的最小处理单元。"""

    seed_id: str
    domain: str
    function: str
    sub_function: str = ""
    standard_utterance: str = ""
    params: Dict[str, str] = field(default_factory=dict)
    source_type: str = "config"

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Seed":
        """从字典创建 Seed 对象。"""
        return cls(
            seed_id=data.get("seed_id", ""),
            domain=data.get("domain", ""),
            function=data.get("function", ""),
            sub_function=data.get("sub_function", ""),
            standard_utterance=data.get("standard_utterance", ""),
            params=data.get("params", {}),
            source_type=data.get("source_type", "config"),
        )


# ---------------------------------------------------------------------------
# 种子引擎
# ---------------------------------------------------------------------------

class SeedEngine:
    """
    种子生成引擎。

    公共接口：
      - generate_from_config(config_path, max_seeds) -> List[Seed]
      - extract_from_excel(excel_path, ...) -> List[Seed]
    """

    def __init__(self, config_loader: Optional[ConfigLoader] = None):
        self._config_loader = config_loader or ConfigLoader()

    # ---- 公共方法 --------------------------------------------------------

    def generate_from_config(
        self,
        config_path: str,
        max_seeds: int = 1000,
    ) -> List[Seed]:
        """
        从功能树 YAML/JSON 配置文件生成种子列表。

        参数:
            config_path: 功能树配置文件路径（YAML 或 JSON）
            max_seeds: 最大种子数量（防止组合爆炸）

        返回:
            种子列表

        异常:
            ValueError: 配置文件格式错误或缺少必要字段
            FileNotFoundError: 配置文件不存在
        """
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_path}")

        with open(path, "r", encoding="utf-8") as f:
            if path.suffix in (".yaml", ".yml"):
                raw_config = yaml.safe_load(f)
            elif path.suffix == ".json":
                raw_config = json.load(f)
            else:
                raise ValueError(f"不支持的配置文件格式: {path.suffix}（仅支持 .yaml/.yml/.json）")

        if not raw_config:
            raise ValueError("配置文件内容为空")

        entries = self._parse_vehicle_tree(raw_config)
        seeds: List[Seed] = []
        global_index = 0

        for entry in entries:
            domain = entry["domain"]
            function = entry["function"]
            sub_function = entry.get("sub_function", "")
            template = entry.get("utterance_template", "")
            param_defs = entry.get("params", {})

            if param_defs:
                combinations = self._combine_params(
                    domain, function, param_defs,
                    max_combinations=max(1, max_seeds // max(len(entries), 1)),
                )
                for combo in combinations:
                    utterance = template
                    for k, v in combo.items():
                        utterance = utterance.replace(f"{{{k}}}", str(v))

                    seed = Seed(
                        seed_id=self._generate_seed_id(domain, function, global_index),
                        domain=domain,
                        function=function,
                        sub_function=sub_function,
                        standard_utterance=utterance,
                        params=combo,
                        source_type="config",
                    )
                    seeds.append(seed)
                    global_index += 1
            else:
                seed = Seed(
                    seed_id=self._generate_seed_id(domain, function, global_index),
                    domain=domain,
                    function=function,
                    sub_function=sub_function,
                    standard_utterance=template,
                    params={},
                    source_type="config",
                )
                seeds.append(seed)
                global_index += 1

            if len(seeds) >= max_seeds:
                break

        seeds = seeds[:max_seeds]
        logger.info("从配置文件生成 %d 个种子 (来源: %s)", len(seeds), config_path)
        return seeds

    def extract_from_excel(
        self,
        excel_path: str,
        domain_col: str = "一级分类",
        function_col: str = "二级分类",
        utterance_col: str = "标准话术",
    ) -> List[Seed]:
        """
        从 Excel 文件中提取种子。

        参数:
            excel_path: Excel 文件路径
            domain_col: 领域列名
            function_col: 功能列名
            utterance_col: 标准话术列名

        返回:
            种子列表

        异常:
            ValueError: Excel 缺少必要列
            FileNotFoundError: 文件不存在
        """
        path = Path(excel_path)
        if not path.exists():
            raise FileNotFoundError(f"Excel 文件不存在: {excel_path}")

        df = pd.read_excel(excel_path)

        # 检查必要列
        missing = []
        for col in [domain_col, utterance_col]:
            if col not in df.columns:
                missing.append(col)
        if missing:
            available = ", ".join(df.columns.tolist())
            raise ValueError(
                f"Excel 缺少必要列: {', '.join(missing)}。"
                f"可用列: {available}"
            )

        seeds: List[Seed] = []
        for idx, row in df.iterrows():
            domain = str(row.get(domain_col, "")).strip()
            function = str(row.get(function_col, "")).strip() if function_col in df.columns else ""
            utterance = str(row.get(utterance_col, "")).strip()

            if not utterance or utterance == "nan":
                continue

            seed = Seed(
                seed_id=self._generate_seed_id(domain, function, idx),
                domain=domain,
                function=function,
                standard_utterance=utterance,
                params={},
                source_type="excel",
            )
            seeds.append(seed)

        logger.info("从 Excel 提取 %d 个种子 (来源: %s)", len(seeds), excel_path)
        return seeds

    # ---- 内部方法 --------------------------------------------------------

    def _parse_vehicle_tree(self, raw_config: Dict) -> List[Dict]:
        """解析功能树配置为标准化的领域-功能-参数结构。"""
        entries = []
        vehicle_tree = raw_config.get("vehicle_tree", raw_config)
        domains = vehicle_tree.get("domains", [])

        if not domains:
            raise ValueError(
                "配置文件缺少 'vehicle_tree.domains' 字段。"
                "请参考 configs/orbit_vehicle_tree_sample.yaml 示例。"
            )

        for domain_def in domains:
            domain_name = domain_def.get("name", "")
            functions = domain_def.get("functions", [])

            for func_def in functions:
                func_name = func_def.get("name", "")
                sub_functions = func_def.get("sub_functions", [])

                if sub_functions:
                    for sub_def in sub_functions:
                        entries.append({
                            "domain": domain_name,
                            "function": func_name,
                            "sub_function": sub_def.get("name", ""),
                            "utterance_template": sub_def.get("utterance_template", ""),
                            "params": sub_def.get("params", {}),
                        })
                else:
                    entries.append({
                        "domain": domain_name,
                        "function": func_name,
                        "sub_function": "",
                        "utterance_template": func_def.get("utterance_template", ""),
                        "params": func_def.get("params", {}),
                    })

        return entries

    def _combine_params(
        self,
        domain: str,
        function: str,
        param_definitions: Dict[str, List[str]],
        max_combinations: int = 100,
    ) -> List[Dict[str, str]]:
        """对参数进行组合（笛卡尔积 + 采样）。"""
        if not param_definitions:
            return [{}]

        keys = list(param_definitions.keys())
        values = [param_definitions[k] for k in keys]

        all_combos = list(itertools.product(*values))

        if len(all_combos) > max_combinations:
            all_combos = random.sample(all_combos, max_combinations)

        return [dict(zip(keys, combo)) for combo in all_combos]

    def _generate_seed_id(self, domain: str, function: str, index: int) -> str:
        """生成种子唯一标识。"""
        # 使用拼音首字母或简写
        d = domain[:2] if domain else "xx"
        f = function[:2] if function else "xx"
        return f"orbit_{d}_{f}_{index:04d}"

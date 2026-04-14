"""
ORBIT 工具集适配器 — 将 car-orbit 工具集注册到 Hermes Agent 的 TOOLSETS。

类似于现有的 toolset_adapter.py，本模块在导入时自动注册工具集。
应在 BatchRunner 实例化之前导入。
"""

import logging

logger = logging.getLogger(__name__)

_CAR_ORBIT_TOOLSET = {
    "tools": [
        "orbit_seed_generate",
        "orbit_generalize",
        "orbit_batch_generalize",
        "orbit_verify",
        "orbit_batch_verify",
    ],
    "description": "Car-ORBIT Agent: 车载座舱话术泛化与级联验证工具集",
}

try:
    from toolsets import TOOLSETS
    if "car-orbit" not in TOOLSETS:
        TOOLSETS["car-orbit"] = _CAR_ORBIT_TOOLSET
        logger.info("已注册 'car-orbit' 工具集")

    try:
        from toolset_distributions import DISTRIBUTIONS
        if "car-orbit" not in DISTRIBUTIONS:
            DISTRIBUTIONS["car-orbit"] = {
                "description": "Car-ORBIT 数据合成工具集",
                "toolsets": {
                    "car-orbit": 1.0,
                },
            }
            logger.info("已注册 'car-orbit' distribution")
    except ImportError:
        logger.debug("toolset_distributions 不可用 — 跳过 distribution 注册")

except ImportError:
    logger.info("hermes-agent 未安装 — 工具集适配器未激活")

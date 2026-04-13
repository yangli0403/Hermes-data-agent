#!/usr/bin/env python3
"""
Toolset Adapter — registers the 'cockpit-data' toolset with hermes-agent.

hermes-agent's toolsets.py defines named groups of tools. The BatchRunner
uses toolset distributions to decide which tools each agent instance gets.
This adapter injects our custom toolset into the hermes-agent registry so
that BatchRunner can resolve 'cockpit-data' as a valid toolset.

This module should be imported before BatchRunner is instantiated.
"""

import logging

logger = logging.getLogger(__name__)

_COCKPIT_TOOLSET = {
    "tools": [
        "cockpit_synthesize",
        "cockpit_validate",
        "cockpit_batch_synthesize",
    ],
    "description": "Cockpit AI utterance synthesis and validation tools",
}

try:
    from toolsets import TOOLSETS
    if "cockpit-data" not in TOOLSETS:
        TOOLSETS["cockpit-data"] = _COCKPIT_TOOLSET
        logger.info("Registered 'cockpit-data' toolset with hermes-agent")

    # Also register a distribution that includes cockpit-data
    try:
        from toolset_distributions import DISTRIBUTIONS
        if "cockpit" not in DISTRIBUTIONS:
            DISTRIBUTIONS["cockpit"] = {
                "description": "Cockpit data synthesis toolset",
                "toolsets": {
                    "cockpit-data": 1.0,  # Always include
                },
            }
            logger.info("Registered 'cockpit' distribution with hermes-agent")
    except ImportError:
        logger.debug("toolset_distributions not available — skipping distribution registration")

except ImportError:
    logger.info("hermes-agent not installed — toolset adapter inactive")

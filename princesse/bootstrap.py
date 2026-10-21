"""Bootstrap: register all built-in tools."""

from __future__ import annotations

from .tools import ToolRegistry
from .capabilities import register_capability_tools
from .execution import register_execution_tools
from .browser import register_browser_tools


def register_default_tools(registry: ToolRegistry | None = None) -> ToolRegistry:
    reg = registry or ToolRegistry.get_instance()
    register_capability_tools(reg)
    register_execution_tools(reg)
    register_browser_tools(reg)
    return reg

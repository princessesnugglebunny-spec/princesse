"""Dynamic tool creation: synthesize a callable from a spec/code string."""

from __future__ import annotations

from typing import Any, Callable

from .tools import ToolRegistry, ToolParameter


class ToolSynthesizer:
    def __init__(self, registry: ToolRegistry | None = None):
        self.registry = registry or ToolRegistry.get_instance()

    def synthesize(self, name: str, code: str, description: str = "",
                  parameters: list[ToolParameter] | None = None) -> Callable:
        namespace: dict[str, Any] = {}
        exec(compile(code, f"<synthesized:{name}>", "exec"), namespace)  # noqa: S102
        # expect a function named 'run' or the first callable
        func = namespace.get("run")
        if func is None:
            callables = [v for v in namespace.values() if callable(v)]
            if not callables:
                raise ValueError("Synthesized code defines no callable")
            func = callables[0]
        self.registry.register_synthesized(name=name, function=func, description=description,
                                         parameters=parameters)
        return func

    def from_template(self, name: str, template: str, **kwargs) -> Callable:
        code = template.format(**kwargs)
        return self.synthesize(name, code, description=f"Synthesized {name}")

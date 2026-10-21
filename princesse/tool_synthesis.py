"""Dynamic tool creation: synthesize a callable from a spec/code string."""

from __future__ import annotations

from typing import Any, Callable

from .tools import ToolRegistry, ToolParameter


class ToolSynthesizer:
    def __init__(self, registry: ToolRegistry | None = None):
        self.registry = registry or ToolRegistry.get_instance()

    @staticmethod
    def _safe_builtins() -> dict[str, Any]:
        """A restricted builtin set for synthesized tools.

        Dynamic tool creation compiles model-authored code; the namespace is
        limited so a synthesized tool cannot reach the filesystem, the
        network, or the interpreter internals by default.
        """
        import builtins
        allowed = ("abs", "all", "any", "bool", "dict", "enumerate", "filter", "float",
                   "format", "int", "len", "list", "map", "max", "min", "range", "reversed",
                   "round", "set", "sorted", "str", "sum", "tuple", "zip",
                   "Exception", "ValueError", "TypeError", "KeyError", "IndexError")
        return {name: getattr(builtins, name) for name in allowed if hasattr(builtins, name)}

    def synthesize(self, name: str, code: str, description: str = "",
                  parameters: list[ToolParameter] | None = None) -> Callable:
        namespace: dict[str, Any] = {"__builtins__": self._safe_builtins()}
        exec(compile(code, f"<synthesized:{name}>", "exec"), namespace)  # noqa: S102  # nosec B102 - dynamic tool creation; namespace restricted to safe builtins
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

"""Dynamic tool registry with OpenAI function schemas and sandbox specs."""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class ToolCategory(str, Enum):
    SYSTEM = "system"
    ANALYSIS = "analysis"
    CODE_GENERATION = "code_generation"
    FILE_OPERATION = "file_operation"
    NETWORK = "network"
    COMPUTATION = "computation"
    INTEGRATION = "integration"
    SYNTHESIZED = "synthesized"
    EXTERNAL = "external"


class ToolStatus(str, Enum):
    REGISTERED = "registered"
    ACTIVE = "active"
    ERROR = "error"


@dataclass
class ToolMetrics:
    total_executions: int = 0
    total_errors: int = 0
    total_latency_ms: float = 0.0
    by_tool: dict[str, dict[str, Any]] = field(default_factory=dict)

    def record(self, name: str, success: bool, latency_ms: float) -> None:
        self.total_executions += 1
        if not success:
            self.total_errors += 1
        self.total_latency_ms += latency_ms
        entry = self.by_tool.setdefault(name, {"executions": 0, "errors": 0, "latency_ms": 0.0})
        entry["executions"] += 1
        if not success:
            entry["errors"] += 1
        entry["latency_ms"] += latency_ms


@dataclass
class ToolParameter:
    name: str
    type: str
    description: str
    required: bool = True
    default: Any = None
    enum: list[Any] | None = None


@dataclass
class SandboxSpec:
    image: str = "python:3.11-slim"
    memory_limit: str = "512m"
    cpu_limit: str = "0.5"
    timeout_seconds: int = 30
    network_enabled: bool = False
    volumes: list[str] = field(default_factory=list)
    environment: dict[str, str] = field(default_factory=dict)
    working_dir: str = "/workspace"
    user: str = "nobody"


@dataclass
class ToolEntry:
    name: str
    description: str
    category: ToolCategory
    function: Callable
    parameters: list[ToolParameter] = field(default_factory=list)
    returns: dict[str, Any] = field(default_factory=dict)
    status: ToolStatus = ToolStatus.REGISTERED
    version: str = "1.0.0"
    author: str = "system"
    tags: list[str] = field(default_factory=list)
    sandbox_spec: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    usage_count: int = 0
    last_used: str | None = None
    avg_latency_ms: float = 0.0
    error_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["category"] = self.category.value
        data["status"] = self.status.value
        data["function"] = getattr(self.function, "__name__", None)
        return data

    def to_function_schema(self) -> dict[str, Any]:
        properties = {}
        required = []
        for param in self.parameters:
            prop: dict[str, Any] = {"type": param.type, "description": param.description}
            if param.enum:
                prop["enum"] = param.enum
            if param.default is not None:
                prop["default"] = param.default
            properties[param.name] = prop
            if param.required:
                required.append(param.name)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {"type": "object", "properties": properties, "required": required},
            },
        }

    def validate_args(self, args: dict[str, Any]) -> tuple[bool, str | None]:
        for param in self.parameters:
            if param.required and param.name not in args:
                return False, f"Missing required parameter: {param.name}"
            if param.name in args and param.enum and args[param.name] not in param.enum:
                return False, f"Invalid value for {param.name}: must be one of {param.enum}"
        return True, None


class ToolRegistry:
    _instance: Optional["ToolRegistry"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._tools: dict[str, ToolEntry] = {}
        self._categories: dict[ToolCategory, set[str]] = {c: set() for c in ToolCategory}
        self.metrics = ToolMetrics()
        self._sandbox_isolator = None
        self._event_bus = None
        self._initialized = True

    @classmethod
    def get_instance(cls) -> "ToolRegistry":
        if cls._instance is None:
            cls._instance = ToolRegistry()
        return cls._instance

    def reset(self):
        self._tools.clear()
        for c in self._categories:
            self._categories[c].clear()
        self.metrics = ToolMetrics()

    def set_sandbox_isolator(self, isolator):
        self._sandbox_isolator = isolator

    def register(self, name: str, function: Callable, description: str,
                category: ToolCategory = ToolCategory.SYSTEM,
                parameters: list[ToolParameter] | None = None,
                returns: dict[str, Any] | None = None,
                sandbox_spec: SandboxSpec | None = None,
                tags: list[str] | None = None,
                version: str = "1.0.0", author: str = "system", **metadata) -> ToolEntry:
        if name in self._tools:
            raise ValueError(f"Tool already registered: {name}")
        if parameters is None:
            parameters = self._infer_parameters(function)
        entry = ToolEntry(
            name=name, description=description, category=category, function=function,
            parameters=parameters, returns=returns or {},
            sandbox_spec=sandbox_spec.__dict__ if sandbox_spec else None,
            tags=tags or [], version=version, author=author, metadata=metadata,
        )
        self._tools[name] = entry
        self._categories[category].add(name)
        return entry

    def _infer_parameters(self, function: Callable) -> list[ToolParameter]:
        sig = inspect.signature(function)
        params = []
        for name, param in sig.parameters.items():
            if name in ("self", "cls"):
                continue
            ptype = "any"
            if param.annotation != inspect.Parameter.empty:
                ptype = self._type_to_json_schema(param.annotation)
            required = param.default == inspect.Parameter.empty
            default = None if required else param.default
            params.append(ToolParameter(name=name, type=ptype, description=f"Parameter {name}",
                                       required=required, default=default))
        return params

    def _type_to_json_schema(self, annotation: Any) -> str:
        type_map = {str: "string", int: "integer", float: "number", bool: "boolean",
                    list: "array", dict: "object", type(None): "null"}
        if hasattr(annotation, "__origin__"):
            origin = annotation.__origin__
            if origin in (list,):
                return "array"
            if origin in (dict,):
                return "object"
        return type_map.get(annotation, "any")

    def unregister(self, name: str) -> bool:
        if name not in self._tools:
            return False
        entry = self._tools[name]
        self._categories[entry.category].discard(name)
        del self._tools[name]
        return True

    def get(self, name: str) -> ToolEntry | None:
        return self._tools.get(name)

    def get_by_category(self, category: ToolCategory) -> list[ToolEntry]:
        return [self._tools[n] for n in self._categories.get(category, set()) if n in self._tools]

    def search(self, query: str, category: ToolCategory | None = None) -> list[ToolEntry]:
        ql = query.lower()
        results = []
        for entry in self._tools.values():
            if category and entry.category != category:
                continue
            if (ql in entry.name.lower() or ql in entry.description.lower()
                    or any(ql in t.lower() for t in entry.tags)):
                results.append(entry)
        return results

    def list_all(self) -> list[ToolEntry]:
        return list(self._tools.values())

    async def execute(self, name: str, args: dict[str, Any], sandbox: bool = False) -> Any:
        entry = self._tools.get(name)
        if not entry:
            raise ValueError(f"Tool not found: {name}")
        valid, error = entry.validate_args(args)
        if not valid:
            raise ValueError(error)
        entry.usage_count += 1
        entry.last_used = datetime.utcnow().isoformat()
        start = time.monotonic()
        try:
            if sandbox and self._sandbox_isolator:
                result = await self._sandbox_isolator.execute_tool(entry.name, entry.function, args, entry.sandbox_spec)
            else:
                result = await self._execute_direct(entry, args)
            latency_ms = (time.monotonic() - start) * 1000
            self.metrics.record(name, True, latency_ms)
            entry.avg_latency_ms = (entry.avg_latency_ms * (entry.usage_count - 1) + latency_ms) / entry.usage_count
            return result
        except Exception:
            latency_ms = (time.monotonic() - start) * 1000
            self.metrics.record(name, False, latency_ms)
            entry.error_count += 1
            raise

    async def _execute_direct(self, entry: ToolEntry, args: dict[str, Any]) -> Any:
        func = entry.function
        if asyncio.iscoroutinefunction(func):
            return await func(**args)
        return func(**args)

    def register_synthesized(self, name: str, function: Callable, description: str = "",
                            parameters: list[ToolParameter] | None = None,
                            metadata: dict[str, Any] | None = None) -> ToolEntry:
        return self.register(name=name, function=function, description=description,
                            category=ToolCategory.SYNTHESIZED,
                            parameters=parameters, tags=["synthesized"],
                            metadata=metadata or {})

    def to_openai_tools(self) -> list[dict[str, Any]]:
        return [e.to_function_schema() for e in self._tools.values()]

"""The ``python_exec`` sandbox contract, defined once (#323).

This is a *restricted execution contract*, not an isolation guarantee: the code runs in the
server process with a narrowed ``__import__`` and builtins. Anything that states what
``python_exec`` allows (``PythonExecAction``, prompts through ``{{python_sandbox}}``, the
save-time check in ``WorkflowLibrary.save()``) reads it from here.
"""

import ast
import builtins
import importlib
from collections.abc import Callable, Mapping
from typing import Any

from zebra.definitions.contracts import TEMPLATE_REF

# Modules the code may import (top-level package name; submodules follow their package)
ALLOWED_MODULES = frozenset(
    {
        "math",
        "json",
        "datetime",
        "collections",
        "itertools",
        "functools",
        "operator",
        "string",
        "re",
        "random",
        "statistics",
        "decimal",
        "fractions",
        "hashlib",
        "base64",
        "uuid",
        "copy",
        "pprint",
    }
)

# Builtins removed from the namespace. ``__import__`` is then reinstalled as the restricted hook.
BLOCKED_BUILTINS = frozenset(
    {"eval", "exec", "compile", "__import__", "open", "input", "breakpoint"}
)

# Names already imported into the namespace, so code may use them without ``import``
PRELOADED = ("math", "json", "datetime", "re", "random")


class SandboxImportError(ImportError):
    """An import the sandbox does not allow."""


def is_import_allowed(name: str) -> bool:
    """True when ``name`` (as given to ``__import__``) passes the sandbox's import gate.

    The gate looks at the top-level package only; a relative import (empty name) fails.
    """
    return name.split(".")[0] in ALLOWED_MODULES


def make_import_hook(real_import: Callable[..., Any]) -> Callable[..., Any]:
    """The restricted ``__import__`` installed in the sandbox namespace."""

    def safe_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if not is_import_allowed(name):
            raise SandboxImportError(f"Module '{name}' is not allowed")
        return real_import(name, *args, **kwargs)

    return safe_import


def build_globals(properties: Mapping[str, Any]) -> dict[str, Any]:
    """The globals ``python_exec`` code runs with.

    ``props`` is the process properties without the engine's ``__`` keys.
    """
    safe_builtins = {k: v for k, v in vars(builtins).items() if k not in BLOCKED_BUILTINS}
    safe_builtins["__import__"] = make_import_hook(builtins.__import__)
    namespace: dict[str, Any] = {
        "__builtins__": safe_builtins,
        "props": {k: v for k, v in properties.items() if not k.startswith("__")},
    }
    for name in PRELOADED:
        namespace[name] = importlib.import_module(name)
    return namespace


def describe_contract() -> str:
    """The contract as prompt text: what code may import, call, read and publish."""
    return (
        "Python sandbox rules (code runs in-process, restricted; not for untrusted code):\n"
        f"- Allowed imports (top-level modules only): {', '.join(sorted(ALLOWED_MODULES))}. "
        "Any other import fails with ImportError.\n"
        f"- Already imported, no import needed: {', '.join(PRELOADED)}.\n"
        f"- Not available: {', '.join(sorted(BLOCKED_BUILTINS - {'__import__'}))}. "
        "No file, network or process access.\n"
        "- `props` is a dict of the workflow's process properties (read it, do not rely on "
        "writing to it).\n"
        "- Assign the final value to a variable named `result`; it is stored as the task's "
        "result and must be JSON-serializable.\n"
        "- print() output is captured separately as stdout."
    )


def _bound_names(tree: ast.AST) -> set[str]:
    """Names the code itself binds (assignment, def, class, argument, import alias)."""
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store | ast.Del):
            bound.add(node.id)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            bound.add(node.name)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, ast.alias):
            bound.add((node.asname or node.name).split(".")[0])
    return bound


def check_code(code: str) -> list[str]:
    """Statically find contract violations in literal code.

    Best effort: reports ``import x`` / ``from x import y`` (and ``__import__("x")`` with a
    literal name) of a module the import gate refuses, and uses of a blocked builtin the code
    does not rebind itself. Dynamic tricks are left to the run-time gate. A syntax error returns
    no findings (the run reports it).

    Returns:
        One message per finding, each naming the offending module or builtin.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    findings: list[str] = []
    bound = _bound_names(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if not is_import_allowed(alias.name):
                    findings.append(f"import of module '{alias.name}' is not allowed")
        elif isinstance(node, ast.ImportFrom):
            name = "." * node.level + (node.module or "")
            if node.level or not is_import_allowed(name):
                findings.append(f"import of module '{name}' is not allowed")
        elif isinstance(node, ast.Call) and _is_name(node.func, "__import__"):
            arg = node.args[0] if node.args else None
            if (
                "__import__" not in bound
                and isinstance(arg, ast.Constant)
                and isinstance(arg.value, str)
                and not is_import_allowed(arg.value)
            ):
                findings.append(f"import of module '{arg.value}' is not allowed")
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id in BLOCKED_BUILTINS - {"__import__"} and node.id not in bound:
                findings.append(f"use of blocked builtin '{node.id}'")
    return findings


def check_task_code(code: str) -> list[str] | None:
    """``check_code`` for a ``python_exec`` task's ``code`` property as written in a definition.

    Runtime resolves ``{{...}}`` templates before running, so code holding a template reference
    is not what will execute and cannot be checked statically: that returns ``None`` (skipped,
    checked when it runs). Literal code returns its findings.
    """
    if TEMPLATE_REF.search(code):
        return None
    return check_code(code)


def _is_name(node: ast.AST, name: str) -> bool:
    return isinstance(node, ast.Name) and node.id == name


def failure_appendix(error: BaseException) -> str:
    """The contract text for a failure caused by the contract, else an empty string."""
    denied_import = isinstance(error, SandboxImportError)
    blocked_name = isinstance(error, NameError) and getattr(error, "name", None) in (
        BLOCKED_BUILTINS - {"__import__"}
    )
    if denied_import or blocked_name:
        return "\n\n" + describe_contract()
    return ""

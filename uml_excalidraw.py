#!/usr/bin/env python3
"""
UML class diagram generator: Python / Java project -> PNG + Excalidraw

Statically analyses a Python and/or Java project (it never executes the
project) and produces:

    <output>.png         -> rendered diagram
    <output>.excalidraw  -> editable Excalidraw scene (optional)

Usage:
    python uml_excalidraw.py                      # analyse the current directory
    python uml_excalidraw.py path/to/project
    python uml_excalidraw.py path/to/project -o docs/uml
    python uml_excalidraw.py . --exclude "tests/*" --no-dependencies --excalidraw

Output paths are resolved relative to the *current working directory*
(never silently inside the analysed project) and are printed relative to it.

What is detected
    * classes, interfaces, enums (incl. constants), records, nested classes
    * class attributes and instance attributes (self.x / this.x)
    * methods with parameters and return types; wide constructors are wrapped
      one parameter per line
    * inheritance, interface realization
    * composition (the class instantiates the part), aggregation (the part is
      injected through a parameter), association (typed attribute) and
      dependency (parameters, return types, object creation)
    * multiplicity (0..*) for collections and arrays

Layout
    Classes are arranged in layers (base classes above subclasses, owners above
    parts), ordered to reduce edge crossings, and connected with orthogonal
    edges routed through lanes between the rows. Unrelated classes are packed
    into a grid at the end.
"""

from __future__ import annotations

import argparse
import ast
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

IGNORE_DIRS = {
    ".git", ".hg", ".svn", ".venv", "venv", "env", "ENV",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "node_modules", "dist", "build", ".tox", ".idea", ".vscode",
    "site-packages", "target", "out",
}

# Defaults (can be overridden from the command line).
DEFAULT_IGNORED_CLASSES = {"Main"}
DEFAULT_IGNORED_TYPES = {"Scanner"}  # e.g. `Scanner sc = new Scanner(System.in);`

PY_ENUM_BASES = {"Enum", "IntEnum", "StrEnum", "Flag", "IntFlag"}

# Text metrics.
FONT_SIZE = 14
TITLE_FONT_SIZE = 18
STEREOTYPE_FONT_SIZE = 12
LABEL_FONT_SIZE = 11
LINE_HEIGHT = 19.0          # pixels per line inside compartments
CHAR_WIDTH = 8.6            # monospace advance at FONT_SIZE (safe estimate)
PAD_X = 14
PAD_Y = 8

# Box geometry.
BOX_MIN_WIDTH = 220
BOX_MAX_WIDTH = 560
MAX_CHARS = int((BOX_MAX_WIDTH - 2 * PAD_X) / CHAR_WIDTH)

# Layout geometry.
HORIZONTAL_GAP = 70
BASE_VERTICAL_GAP = 90
LANE_SPACING = 12
CANVAS_MARGIN = 60
BLOCK_GAP = 100
DEFAULT_MAX_ROW_WIDTH = 3200

HIERARCHY_KINDS = {"inheritance", "realization"}

MONO_FONT = "DejaVu Sans Mono, Menlo, Consolas, Courier New, monospace"


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #

@dataclass
class FieldInfo:
    name: str
    type_name: str = ""
    visibility: str = "+"
    default: str | None = None
    source: str = "instance"  # "class" | "instance" | "enum"


@dataclass
class MethodInfo:
    name: str
    visibility: str
    parameters: list[str] = field(default_factory=list)
    return_type: str = ""
    is_static: bool = False
    is_classmethod: bool = False
    is_property: bool = False
    is_async: bool = False
    is_abstract: bool = False


@dataclass
class ClassInfo:
    name: str
    module: str
    qualname: str
    file: str
    lineno: int
    kind: str = "class"  # class | interface | enum | record
    is_abstract: bool = False
    extra_stereotypes: list[str] = field(default_factory=list)
    bases: list[str] = field(default_factory=list)
    interfaces: list[str] = field(default_factory=list)
    imports: dict[str, str] = field(default_factory=dict)
    fields: list[FieldInfo] = field(default_factory=list)
    methods: list[MethodInfo] = field(default_factory=list)
    # (field name, type name, kind)
    field_relations: list[tuple[str, str, str]] = field(default_factory=list)
    used_types: set[str] = field(default_factory=set)
    # Java only: (kind, field, type, explicit_this) resolved once all members are known
    pending: list[tuple[str, str, str, bool]] = field(default_factory=list)


@dataclass
class Relation:
    source: str
    target: str
    kind: str
    label: str = ""
    multiplicity: str = ""

    def priority(self) -> int:
        return {
            "inheritance": 100,
            "realization": 95,
            "composition": 80,
            "aggregation": 70,
            "association": 60,
            "dependency": 40,
        }.get(self.kind, 0)


# --------------------------------------------------------------------------- #
# Source analysis
# --------------------------------------------------------------------------- #

_JAVA_LEXICAL = re.compile(
    r'//[^\n]*|/\*[\s\S]*?\*/|"""[\s\S]*?"""|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\''
)
_JAVA_ANNOTATION = re.compile(
    r'@(?!interface\b)[A-Za-z_$][\w$.]*(?:\s*\((?:[^()]|\([^()]*\))*\))?'
)
_JAVA_MODIFIERS = re.compile(
    r'\b(static|final|transient|volatile|public|protected|private|abstract|'
    r'synchronized|native|strictfp|default|sealed|non-sealed)\b'
)
_JAVA_TYPE_DECL = re.compile(r'\b(class|interface|enum|record)\s+([A-Za-z_$][\w$]*)')
_QUALIFIED = r'[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*'
_MANY_TYPE = re.compile(
    r'(?i)(?:list|set|tuple|dict|map|queue|deque|stack|vector|collection|iterable|sequence)\s*[\[<]'
    r'|\[\s*\]\s*$|^(?:list|set|frozenset|tuple|dict)$'
)


class ProjectAnalyzer:
    def __init__(
        self,
        root: Path,
        include_private: bool = True,
        excluded_patterns: list[str] | None = None,
        ignored_classes: set[str] | None = None,
        ignored_types: set[str] | None = None,
    ):
        self.root = root.resolve()
        self.include_private = include_private
        self.script_path = Path(__file__).resolve()
        self.excluded_patterns = excluded_patterns or []
        self.ignored_classes = set(DEFAULT_IGNORED_CLASSES if ignored_classes is None else ignored_classes)
        self.ignored_types = set(DEFAULT_IGNORED_TYPES if ignored_types is None else ignored_types)
        self.classes: dict[str, ClassInfo] = {}
        self.short_name_to_qualified: dict[str, list[str]] = {}
        self.errors: list[str] = []
        self.scanned_files: list[str] = []
        self.ignored_files: list[str] = []

    # ---------------------------------------------------------------- driver

    def analyze(self) -> tuple[dict[str, ClassInfo], list[Relation]]:
        for path in self._iter_source_files():
            rel = path.relative_to(self.root).as_posix()
            if self._is_excluded(path, rel):
                self.ignored_files.append(rel)
                continue
            self.scanned_files.append(rel)
            self._parse_file(path)

        self._build_name_index()
        return self.classes, self._infer_relations()

    def _iter_source_files(self):
        found: list[Path] = []
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = sorted(
                d for d in dirnames
                if d not in IGNORE_DIRS and not d.endswith(".egg-info") and not d.startswith(".")
            )
            for filename in filenames:
                if filename.lower().endswith((".py", ".java")):
                    found.append(Path(dirpath) / filename)
        return sorted(found, key=lambda p: p.as_posix().lower())

    def _is_excluded(self, path: Path, rel: str) -> bool:
        # Never analyse this generator, even when it lives inside the project.
        try:
            if path.resolve() == self.script_path:
                return True
        except OSError:
            pass
        for pattern in self.excluded_patterns:
            if fnmatch(rel, pattern) or fnmatch(Path(rel).name, pattern):
                return True
            if pattern.startswith("**/") and fnmatch(rel, pattern[3:]):
                return True
        return False

    def _module_name(self, path: Path) -> str:
        parts = list(path.relative_to(self.root).with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts) if parts else self.root.name

    def _parse_file(self, path: Path) -> None:
        try:
            try:
                source = path.read_text(encoding="utf-8-sig")
            except UnicodeDecodeError:
                source = path.read_text(encoding="latin-1")
        except Exception as exc:
            self.errors.append(f"{path}: could not be read ({exc})")
            return

        if path.suffix.lower() == ".java":
            self._parse_java_file(path, source)
            return

        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            self.errors.append(f"{path}:{exc.lineno}: invalid syntax")
            return

        module = self._module_name(path)
        imports = self._collect_python_imports(tree, module, path.stem == "__init__")
        self._walk_python_body(tree.body, module, path, imports, [])

    # ------------------------------------------------------- name resolution

    def _build_name_index(self) -> None:
        for qualname, info in self.classes.items():
            self.short_name_to_qualified.setdefault(info.name, []).append(qualname)

    def _match_qualified(self, dotted: str) -> str | None:
        if dotted in self.classes:
            return dotted
        suffix = "." + dotted
        matches = [q for q in self.classes if q.endswith(suffix)]
        if len(matches) == 1:
            return matches[0]
        parts = dotted.split(".")
        for i in range(1, max(1, len(parts) - 1)):
            tail = ".".join(parts[i:])
            if tail in self.classes:
                return tail
            matches = [q for q in self.classes if q.endswith("." + tail)]
            if len(matches) == 1:
                return matches[0]
        return None

    def _resolve_internal(self, name: str, info: ClassInfo) -> str | None:
        if not name:
            return None
        clean = re.split(r"[\[<]", name.strip().strip("'\""), maxsplit=1)[0].strip()
        if not clean:
            return None

        if clean in self.classes:
            return clean

        # Enclosing scopes: nested classes, then the module / package.
        parts = info.qualname.split(".")
        for k in range(len(parts), 0, -1):
            candidate = ".".join(parts[:k]) + "." + clean
            if candidate in self.classes:
                return candidate

        # Through the import table.
        head, _, rest = clean.partition(".")
        if head in info.imports:
            dotted = info.imports[head] + ("." + rest if rest else "")
            found = self._match_qualified(dotted)
            if found:
                return found

        short = clean.rsplit(".", 1)[-1]
        candidates = self.short_name_to_qualified.get(short, [])
        if len(candidates) == 1:
            return candidates[0]
        same_module = [q for q in candidates if self.classes[q].module == info.module]
        if len(same_module) == 1:
            return same_module[0]
        return None

    # -------------------------------------------------------------- relations

    @staticmethod
    def _is_many(type_text: str) -> bool:
        return bool(type_text and _MANY_TYPE.search(type_text.strip()))

    def _infer_relations(self) -> list[Relation]:
        dedup: dict[tuple[str, str], Relation] = {}

        def link(info: ClassInfo, type_name: str, kind: str, label: str = "", many: bool = False) -> None:
            target = self._resolve_internal(type_name, info)
            if not target or target == info.qualname:
                return
            if kind == "inheritance" and self.classes[target].kind == "interface" and info.kind != "interface":
                kind = "realization"
            self._merge_relation(dedup, Relation(info.qualname, target, kind, label, "0..*" if many else ""))

        for info in self.classes.values():
            for base in info.bases:
                link(info, base, "inheritance")
            for iface in info.interfaces:
                link(info, iface, "realization")

            field_types = {f.name: f.type_name for f in info.fields}
            for field_name, type_name, kind in info.field_relations:
                link(info, type_name, kind, field_name, self._is_many(field_types.get(field_name, "")))

            for f in info.fields:
                if f.source == "enum":
                    continue
                for type_name in self._type_names(f.type_name):
                    link(info, type_name, "association", f.name, self._is_many(f.type_name))

            for method in info.methods:
                for param in method.parameters:
                    for type_name in self._type_names_from_display_signature(param):
                        link(info, type_name, "dependency")
                for type_name in self._type_names(method.return_type):
                    link(info, type_name, "dependency")

            for used in info.used_types:
                link(info, used, "dependency")

        return sorted(dedup.values(), key=lambda r: (r.source, r.target, -r.priority(), r.kind))

    @staticmethod
    def _merge_relation(dedup: dict[tuple[str, str], Relation], new: Relation) -> None:
        key = (new.source, new.target)
        old = dedup.get(key)
        if old is None:
            dedup[key] = new
        elif new.priority() > old.priority():
            if not new.label and old.label:
                new.label, new.multiplicity = old.label, old.multiplicity
            dedup[key] = new
        elif not old.label and new.label:
            old.label, old.multiplicity = new.label, new.multiplicity

    # ------------------------------------------------------------ shared utils

    @staticmethod
    def _type_names(type_text: str) -> set[str]:
        if not type_text:
            return set()
        return set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_.]*\b", type_text))

    def _type_names_from_display_signature(self, text: str) -> set[str]:
        if ":" not in text:
            return set()
        return self._type_names(text.split(":", 1)[1].split("=", 1)[0].strip())

    @staticmethod
    def _truncate(text: str, size: int) -> str:
        text = " ".join(text.split())
        return text if len(text) <= size else text[: size - 1] + "…"

    # =========================================================== Python parser

    def _collect_python_imports(self, tree: ast.AST, module: str, is_package: bool) -> dict[str, str]:
        result: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.asname:
                        result[alias.asname] = alias.name
                    else:
                        head = alias.name.split(".")[0]
                        result[head] = head
            elif isinstance(node, ast.ImportFrom):
                base_parts: list[str]
                if node.level:
                    pkg = module.split(".") if module else []
                    if not is_package and pkg:
                        pkg = pkg[:-1]
                    if node.level > 1:
                        pkg = pkg[: max(0, len(pkg) - (node.level - 1))]
                    base_parts = pkg + (node.module.split(".") if node.module else [])
                else:
                    base_parts = node.module.split(".") if node.module else []
                base = ".".join(base_parts)
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    result[alias.asname or alias.name] = f"{base}.{alias.name}" if base else alias.name
        return result

    def _walk_python_body(self, body, module, path, imports, outer) -> None:
        for stmt in body:
            if isinstance(stmt, ast.ClassDef):
                self._extract_python_class(stmt, module, path, imports, outer)
            elif isinstance(stmt, (ast.If, ast.Try, ast.With, ast.AsyncWith)) or type(stmt).__name__ == "TryStar":
                for attr in ("body", "orelse", "finalbody"):
                    self._walk_python_body(getattr(stmt, attr, []) or [], module, path, imports, outer)
                for handler in getattr(stmt, "handlers", []) or []:
                    self._walk_python_body(handler.body, module, path, imports, outer)

    def _extract_python_class(self, node: ast.ClassDef, module, path, imports, outer) -> None:
        chain = [*outer, node.name]
        qualname = ".".join(p for p in [module, *chain] if p)
        info = ClassInfo(
            name=node.name,
            module=module,
            qualname=qualname,
            file=path.relative_to(self.root).as_posix(),
            lineno=getattr(node, "lineno", 0),
            imports=imports,
        )
        info.bases = [n for n in (self._expr_name(b) for b in node.bases) if n]
        base_short = {b.rsplit(".", 1)[-1] for b in info.bases}
        if base_short & PY_ENUM_BASES:
            info.kind = "enum"
        elif "Protocol" in base_short:
            info.kind = "interface"
        if "ABC" in base_short or any(
            kw.arg == "metaclass" and "ABCMeta" in self._expr_name(kw.value) for kw in node.keywords
        ):
            info.is_abstract = True
        if any(self._decorator_name(d).rsplit(".", 1)[-1] == "dataclass" for d in node.decorator_list):
            info.extra_stereotypes.append("dataclass")

        field_map: dict[str, FieldInfo] = {}
        method_nodes: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
        is_enum = info.kind == "enum"

        for stmt in node.body:
            if isinstance(stmt, ast.ClassDef):
                self._extract_python_class(stmt, module, path, imports, chain)
            elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                name = stmt.target.id
                if self._skip_python_attr(name):
                    continue
                field_map[name] = FieldInfo(
                    name=name,
                    type_name=self._format_annotation(stmt.annotation),
                    visibility=self._visibility(name),
                    default=self._safe_unparse(stmt.value) if stmt.value else None,
                    source="enum" if is_enum else "class",
                )
            elif isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Name) and not self._skip_python_attr(target.id):
                        field_map.setdefault(
                            target.id,
                            FieldInfo(
                                name=target.id,
                                type_name="" if is_enum else self._infer_value_type(stmt.value),
                                visibility=self._visibility(target.id),
                                default=self._safe_unparse(stmt.value),
                                source="enum" if is_enum else "class",
                            ),
                        )
            elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method_nodes.append(stmt)

        for fn in method_nodes:
            param_types = self._param_annotations(fn)

            for sub in ast.walk(fn):
                if isinstance(sub, ast.Assign):
                    targets, value, annotation = sub.targets, sub.value, None
                elif isinstance(sub, ast.AnnAssign):
                    targets, value, annotation = [sub.target], sub.value, sub.annotation
                else:
                    continue
                for target in self._flatten_targets(targets):
                    if not (
                        isinstance(target, ast.Attribute)
                        and isinstance(target.value, ast.Name)
                        and target.value.id == "self"
                    ):
                        continue
                    name = target.attr
                    if self._skip_python_attr(name):
                        continue

                    leaves = self._leaves(value)
                    type_name = ""
                    if annotation is not None:
                        type_name = self._format_annotation(annotation)
                    elif len(leaves) == 1 and isinstance(leaves[0], ast.Name) and leaves[0].id in param_types:
                        type_name = param_types[leaves[0].id]
                    else:
                        type_name = self._infer_value_type(value)

                    if name not in field_map:
                        field_map[name] = FieldInfo(
                            name=name,
                            type_name=type_name,
                            visibility=self._visibility(name),
                            default=None,
                            source="instance",
                        )
                    elif not field_map[name].type_name and type_name:
                        field_map[name].type_name = type_name

                    for leaf in leaves:
                        if isinstance(leaf, ast.Call):
                            constructed = self._called_class_name(leaf)
                            if constructed:
                                info.field_relations.append((name, constructed, "composition"))
                        elif isinstance(leaf, ast.Name) and leaf.id in param_types:
                            for tn in self._type_names(param_types[leaf.id]):
                                info.field_relations.append((name, tn, "aggregation"))

            for sub in ast.walk(fn):
                if isinstance(sub, ast.Call):
                    called = self._called_class_name(sub)
                    if called:
                        info.used_types.add(called)

            method_info = self._method_info(fn)
            if method_info:
                info.methods.append(method_info)
                if method_info.is_abstract:
                    info.is_abstract = True
                info.used_types.update(self._names_from_method_signature(fn))

        info.fields = list(field_map.values())
        # Constructor first, everything else in source order.
        info.methods.sort(key=lambda m: m.name != "__init__")
        self.classes[info.qualname] = info

    @staticmethod
    def _skip_python_attr(name: str) -> bool:
        return name.startswith("__") and name.endswith("__")

    def _skip_hidden(self, name: str) -> bool:
        return (not self.include_private) and name.startswith("_") and not (
            name.startswith("__") and name.endswith("__")
        )

    @staticmethod
    def _flatten_targets(targets):
        out = []
        stack = list(targets)
        while stack:
            t = stack.pop(0)
            if isinstance(t, (ast.Tuple, ast.List)):
                stack = list(t.elts) + stack
            elif isinstance(t, ast.Starred):
                stack.insert(0, t.value)
            else:
                out.append(t)
        return out

    @staticmethod
    def _leaves(node: ast.AST | None) -> list[ast.AST]:
        """Leaves of `a or b`, `x if c else y` expressions."""
        if node is None:
            return []
        if isinstance(node, ast.BoolOp):
            return [leaf for v in node.values for leaf in ProjectAnalyzer._leaves(v)]
        if isinstance(node, ast.IfExp):
            return ProjectAnalyzer._leaves(node.body) + ProjectAnalyzer._leaves(node.orelse)
        return [node]

    def _param_annotations(self, fn) -> dict[str, str]:
        args = list(fn.args.posonlyargs) + list(fn.args.args) + list(fn.args.kwonlyargs)
        if fn.args.vararg:
            args.append(fn.args.vararg)
        if fn.args.kwarg:
            args.append(fn.args.kwarg)
        return {a.arg: self._format_annotation(a.annotation) for a in args if a.annotation is not None}

    def _decorator_name(self, node: ast.AST) -> str:
        if isinstance(node, ast.Call):
            node = node.func
        return self._expr_name(node)

    def _method_info(self, fn) -> MethodInfo | None:
        name = fn.name
        decorators = [self._decorator_name(d) for d in fn.decorator_list]
        short = {d.rsplit(".", 1)[-1] for d in decorators}
        if any(d.endswith((".setter", ".deleter")) for d in decorators) or "overload" in short:
            return None
        if self._skip_hidden(name):
            return None

        ret = ""
        if name != "__init__" and fn.returns is not None:
            ret = self._format_annotation(fn.returns)

        return MethodInfo(
            name=name,
            visibility=self._visibility(name),
            parameters=self._format_parameters(fn.args),
            return_type=ret,
            is_static="staticmethod" in short,
            is_classmethod="classmethod" in short,
            is_property=bool(short & {"property", "cached_property"}),
            is_async=isinstance(fn, ast.AsyncFunctionDef),
            is_abstract="abstractmethod" in short,
        )

    def _format_parameters(self, args: ast.arguments) -> list[str]:
        regular = list(args.posonlyargs) + list(args.args)
        defaults = [None] * (len(regular) - len(args.defaults)) + list(args.defaults)
        result: list[str] = []

        def render(arg: ast.arg, default, prefix: str = "") -> str:
            text = prefix + arg.arg
            if arg.annotation is not None:
                text += f": {self._format_annotation(arg.annotation)}"
            if default is not None:
                value = self._safe_unparse(default, 30)
                if value:
                    text += f" = {value}"
            return text

        for arg, default in zip(regular, defaults):
            if arg.arg in {"self", "cls"}:
                continue
            result.append(render(arg, default))
        if args.vararg:
            result.append(render(args.vararg, None, "*"))
        for arg, default in zip(args.kwonlyargs, args.kw_defaults):
            result.append(render(arg, default))
        if args.kwarg:
            result.append(render(args.kwarg, None, "**"))
        return result

    def _names_from_method_signature(self, fn) -> set[str]:
        names: set[str] = set()
        for text in self._param_annotations(fn).values():
            names.update(self._type_names(text))
        if fn.returns is not None:
            names.update(self._type_names(self._format_annotation(fn.returns)))
        return names

    @staticmethod
    def _called_class_name(node: ast.AST | None) -> str | None:
        if not isinstance(node, ast.Call):
            return None
        func = node.func
        if isinstance(func, (ast.Name, ast.Attribute)):
            return ProjectAnalyzer._expr_name(func) or None
        return None

    @staticmethod
    def _expr_name(node: ast.AST | None) -> str:
        if node is None:
            return ""
        try:
            if isinstance(node, ast.Name):
                return node.id
            if isinstance(node, ast.Attribute):
                parent = ProjectAnalyzer._expr_name(node.value)
                return f"{parent}.{node.attr}" if parent else node.attr
            if isinstance(node, ast.Subscript):
                return ProjectAnalyzer._expr_name(node.value)
            if isinstance(node, ast.Constant):
                return str(node.value)
            return ast.unparse(node)
        except Exception:
            return ""

    @staticmethod
    def _format_annotation(node: ast.AST | None) -> str:
        if node is None:
            return ""
        try:
            return ProjectAnalyzer._truncate(ast.unparse(node), 60)
        except Exception:
            return ""

    @staticmethod
    def _infer_value_type(node: ast.AST | None) -> str:
        if node is None:
            return ""
        leaves = ProjectAnalyzer._leaves(node)
        if len(leaves) > 1:
            for leaf in leaves:
                if isinstance(leaf, ast.Call):
                    return ProjectAnalyzer._expr_name(leaf.func)
            return ""
        node = leaves[0]
        if isinstance(node, ast.Call):
            return ProjectAnalyzer._expr_name(node.func)
        if isinstance(node, ast.Constant):
            return "None" if node.value is None else type(node.value).__name__
        if isinstance(node, (ast.List, ast.ListComp)):
            return "list"
        if isinstance(node, (ast.Set, ast.SetComp)):
            return "set"
        if isinstance(node, (ast.Dict, ast.DictComp)):
            return "dict"
        if isinstance(node, ast.Tuple):
            return "tuple"
        return ""

    @staticmethod
    def _safe_unparse(node: ast.AST | None, size: int = 35) -> str | None:
        if node is None:
            return None
        try:
            return ProjectAnalyzer._truncate(ast.unparse(node), size)
        except Exception:
            return None

    @staticmethod
    def _visibility(name: str) -> str:
        if name.startswith("__") and name.endswith("__"):
            return "+"
        if name.startswith("__"):
            return "-"
        if name.startswith("_"):
            return "#"
        return "+"

    # ============================================================ Java parser

    @staticmethod
    def _blank(text: str) -> str:
        return "".join("\n" if ch == "\n" else " " for ch in text)

    def _java_views(self, source: str) -> tuple[str, str]:
        """Return (masked, code), both with exactly the same length as `source`.

        masked: comments and string/char literals blanked (safe for structural scans)
        code:   only comments blanked (string literals preserved, for default values)
        """
        def masked_repl(m: re.Match[str]) -> str:
            return self._blank(m.group(0))

        def code_repl(m: re.Match[str]) -> str:
            value = m.group(0)
            return self._blank(value) if value.startswith(("//", "/*")) else value

        return _JAVA_LEXICAL.sub(masked_repl, source), _JAVA_LEXICAL.sub(code_repl, source)

    @staticmethod
    def _blank_pattern(pattern: re.Pattern[str], masked: str, code: str) -> tuple[str, str]:
        for m in reversed(list(pattern.finditer(masked))):
            s, e = m.span()
            masked = masked[:s] + " " * (e - s) + masked[e:]
            code = code[:s] + " " * (e - s) + code[e:]
        return masked, code

    @staticmethod
    def _find_matching_brace(text: str, open_index: int) -> int:
        depth = 0
        for i in range(open_index, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    return i
        return -1

    @staticmethod
    def _split_spans(text: str, delimiter: str = ",") -> list[tuple[int, int]]:
        """Split at top level (ignoring (), [], {} and generic <...>)."""
        spans: list[tuple[int, int]] = []
        start = 0
        depth = angle = 0
        for i, ch in enumerate(text):
            prev = text[i - 1] if i else ""
            nxt = text[i + 1] if i + 1 < len(text) else ""
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth = max(0, depth - 1)
            elif ch == "<" and (prev.isalnum() or prev in "_$") and (nxt.isupper() or nxt in "?_$"):
                angle += 1
            elif ch == ">" and angle and prev != "-":
                angle -= 1
            elif ch == delimiter and depth == 0 and angle == 0:
                spans.append((start, i))
                start = i + 1
        if text[start:].strip():
            spans.append((start, len(text)))
        return spans

    def _split_java_top_level(self, text: str, delimiter: str = ",") -> list[str]:
        return [text[s:e].strip() for s, e in self._split_spans(text, delimiter) if text[s:e].strip()]

    @staticmethod
    def _has_top_level_assignment(text: str) -> bool:
        depth = 0
        for i, ch in enumerate(text):
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth = max(0, depth - 1)
            elif ch == "=" and depth == 0:
                prev = text[i - 1] if i else ""
                nxt = text[i + 1] if i + 1 < len(text) else ""
                if (prev and prev in "=!<>") or nxt == "=":
                    continue
                return True
        return False

    @staticmethod
    def _remove_angles(text: str) -> str:
        previous = None
        while previous != text:
            previous = text
            text = re.sub(r"<[^<>]*>", " ", text)
        return text

    @staticmethod
    def _java_visibility(text: str, kind: str = "class") -> str:
        if re.search(r"\bprivate\b", text):
            return "-"
        if re.search(r"\bprotected\b", text):
            return "#"
        if re.search(r"\bpublic\b", text) or kind == "interface":
            return "+"
        return "~"

    @staticmethod
    def _java_type_name(type_text: str) -> str:
        type_text = _JAVA_ANNOTATION.sub(" ", type_text)
        type_text = _JAVA_MODIFIERS.sub(" ", type_text)
        return " ".join(type_text.replace("...", "[]").split())

    def _parse_java_file(self, path: Path, source: str) -> None:
        masked, code = self._java_views(source)
        rel_dir = path.parent.relative_to(self.root).as_posix()
        package_match = re.search(r"\bpackage\s+([\w$.]+)\s*;", masked)
        package = (
            package_match.group(1)
            if package_match
            else ("" if rel_dir == "." else rel_dir.replace("/", "."))
        )

        imports: dict[str, str] = {}
        for m in re.finditer(r"\bimport\s+(?!static\b)([\w$.]+)\s*;", masked):
            dotted = m.group(1)
            imports[dotted.rsplit(".", 1)[-1]] = dotted

        declarations: list[dict] = []
        for match in _JAVA_TYPE_DECL.finditer(masked):
            if masked[max(0, match.start() - 1):match.start()] == ".":
                continue
            open_index = masked.find("{", match.end())
            if open_index < 0 or ";" in masked[match.end():open_index]:
                continue
            close_index = self._find_matching_brace(masked, open_index)
            if close_index < 0:
                self.errors.append(f"{path}:{source.count(chr(10), 0, match.start()) + 1}: unbalanced braces")
                continue
            declarations.append({
                "kind": match.group(1),
                "name": match.group(2),
                "header": masked[match.end():open_index].strip(),
                "open": open_index,
                "close": close_index,
                "start": match.start(),
            })

        declarations = [d for d in declarations if not (d["kind"] == "class" and d["name"] in self.ignored_classes)]
        if not declarations:
            return

        for decl in declarations:
            parents = [o for o in declarations if o["open"] < decl["start"] < o["close"]]
            decl["parent"] = min(parents, key=lambda d: d["close"] - d["open"]) if parents else None

        for decl in declarations:
            chain: list[str] = []
            parent = decl.get("parent")
            while parent is not None:
                chain.append(parent["name"])
                parent = parent.get("parent")
            chain.reverse()
            chain.append(decl["name"])
            qualname = ".".join(([package] if package else []) + chain)

            info = ClassInfo(
                name=decl["name"],
                module=package,
                qualname=qualname,
                file=path.relative_to(self.root).as_posix(),
                lineno=source.count("\n", 0, decl["start"]) + 1,
                kind=decl["kind"],
                imports=imports,
            )

            line_start = max(masked.rfind(";", 0, decl["start"]), masked.rfind("{", 0, decl["start"]),
                             masked.rfind("}", 0, decl["start"]))
            if re.search(r"\babstract\b", masked[line_start + 1:decl["start"]]):
                info.is_abstract = True

            header = _JAVA_ANNOTATION.sub(" ", decl["header"])
            record_components = ""
            if decl["kind"] == "record" and "(" in header:
                p_open = header.index("(")
                depth = 0
                p_close = -1
                for idx in range(p_open, len(header)):
                    if header[idx] == "(":
                        depth += 1
                    elif header[idx] == ")":
                        depth -= 1
                        if depth == 0:
                            p_close = idx
                            break
                if p_close > p_open:
                    record_components = code[decl["open"] - len(decl["header"]) - 1 + 0:0]  # placeholder, replaced below
                    record_components = header[p_open + 1:p_close]
                    header = header[:p_open] + " " + header[p_close + 1:]

            flat = " ".join(self._remove_angles(header).split())
            flat = re.sub(r"\bpermits\b.*$", "", flat)
            ext = re.search(r"\bextends\s+(.+?)(?=\bimplements\b|$)", flat)
            impl = re.search(r"\bimplements\s+(.+)$", flat)
            if ext:
                info.bases = [self._java_type_name(x) for x in self._split_java_top_level(ext.group(1))]
            if impl:
                info.interfaces = [self._java_type_name(x) for x in self._split_java_top_level(impl.group(1))]

            for part in self._format_java_parameters(record_components):
                name, _, type_name = part.partition(": ")
                info.fields.append(FieldInfo(name, type_name, "-", source="instance"))
                info.used_types.update(self._type_names(type_name))

            self._parse_java_members(info, code, masked, decl["open"] + 1, decl["close"])
            self.classes[qualname] = info

    def _parse_enum_constants(self, info: ClassInfo, masked: str, start: int, end: int) -> int:
        depth = 0
        semi = -1
        for i in range(start, end):
            ch = masked[i]
            if ch in "({[":
                depth += 1
            elif ch in ")}]":
                depth -= 1
            elif ch == ";" and depth == 0:
                semi = i
                break
        segment_end = semi if semi >= 0 else end
        segment = _JAVA_ANNOTATION.sub(" ", masked[start:segment_end])
        for part in self._split_java_top_level(segment):
            m = re.match(r"\s*([A-Za-z_$][\w$]*)", part)
            if m:
                info.fields.append(FieldInfo(m.group(1), "", "+", source="enum"))
        return semi + 1 if semi >= 0 else end

    def _parse_java_members(self, info: ClassInfo, code: str, masked: str, start: int, end: int) -> None:
        i = start
        if info.kind == "enum":
            i = self._parse_enum_constants(info, masked, start, end)
        member_start = i
        paren = bracket = 0

        while i < end:
            ch = masked[i]
            if ch == "(":
                paren += 1
            elif ch == ")":
                paren = max(0, paren - 1)
            elif ch == "[":
                bracket += 1
            elif ch == "]":
                bracket = max(0, bracket - 1)
            elif ch == "{" and paren == 0 and bracket == 0:
                prefix = masked[member_start:i].strip()
                close = self._find_matching_brace(masked, i)
                if close < 0 or close > end:
                    break
                if self._has_top_level_assignment(prefix):
                    # Array initialiser, anonymous class or lambda inside a field initialiser:
                    # the declaration continues until the next ';'.
                    i = close + 1
                    continue
                if _JAVA_TYPE_DECL.search(prefix):
                    i = close + 1
                    member_start = i
                    continue
                if "(" in prefix:
                    self._parse_java_method(info, code[member_start:i], masked[i + 1:close])
                i = close + 1
                member_start = i
                continue
            elif ch == ";" and paren == 0 and bracket == 0:
                masked_prefix = masked[member_start:i].strip()
                if masked_prefix:
                    if "(" in masked_prefix and not self._has_top_level_assignment(masked_prefix):
                        self._parse_java_method(info, code[member_start:i], "")
                    else:
                        self._parse_java_fields(info, code[member_start:i], masked[member_start:i])
                i += 1
                member_start = i
                continue
            i += 1

        # Resolve relations that depend on knowing all fields.
        field_types = {f.name: f.type_name for f in info.fields}
        for kind, field_name, type_name, explicit in info.pending:
            if kind == "composition" and (explicit or field_name in field_types):
                info.field_relations.append((field_name, type_name, "composition"))
                info.used_types.add(type_name)
            elif kind == "aggregation" and field_name in field_types:
                for tn in self._type_names(field_types[field_name]):
                    info.field_relations.append((field_name, tn, "aggregation"))
        info.pending.clear()

        # Constructors first, then source order.
        info.methods.sort(key=lambda m: m.name != info.name)

    def _parse_java_fields(self, info: ClassInfo, code: str, masked: str) -> None:
        masked, code = self._blank_pattern(_JAVA_ANNOTATION, masked, code)
        visibility = self._java_visibility(masked, info.kind)
        masked, code = self._blank_pattern(_JAVA_MODIFIERS, masked, code)
        if not masked.strip():
            return

        spans = self._split_spans(masked)
        parts = [code[s:e].strip() for s, e in spans]
        if not parts:
            return
        first = re.match(r"^(.+?)\s+([A-Za-z_$][\w$]*)\s*(?:=(.*))?$", parts[0], re.S)
        if not first:
            return
        type_name, first_name, first_default = first.groups()
        type_name = self._java_type_name(type_name)

        # Standard-input helpers (e.g. Scanner sc = new Scanner(System.in)) are noise.
        if (
            type_name in self.ignored_types
            and first_default
            and re.search(rf"\bnew\s+{re.escape(type_name)}\s*\(", first_default)
        ):
            return

        for idx, part in enumerate(parts):
            if idx == 0:
                name, default = first_name, first_default
            else:
                m = re.match(r"^([A-Za-z_$][\w$]*)\s*(?:=(.*))?$", part, re.S)
                if not m:
                    continue
                name, default = m.groups()
            if not self.include_private and visibility in {"-", "#"}:
                continue
            info.fields.append(FieldInfo(
                name=name,
                type_name=type_name or "",
                visibility=visibility,
                default=self._truncate(default or "", 35) or None,
                source="class",
            ))
            if default:
                new_match = re.search(rf"\bnew\s+({_QUALIFIED})", default)
                if new_match:
                    target = self._java_type_name(new_match.group(1))
                    info.field_relations.append((name, target, "composition"))
                    info.used_types.add(target)

        for ref in self._type_names(type_name):
            if ref not in self.ignored_types:
                info.used_types.add(ref)

    @staticmethod
    def _java_matching_paren(text: str, open_index: int) -> int:
        depth = 0
        for i in range(open_index, len(text)):
            if text[i] == "(":
                depth += 1
            elif text[i] == ")":
                depth -= 1
                if depth == 0:
                    return i
        return -1

    def _parse_java_method(self, info: ClassInfo, signature: str, body: str) -> None:
        signature = " ".join(_JAVA_ANNOTATION.sub(" ", signature).split())
        open_paren = signature.find("(")
        if open_paren < 0:
            return
        close_paren = self._java_matching_paren(signature, open_paren)
        if close_paren < 0:
            return
        before = signature[:open_paren].strip()
        params_text = signature[open_paren + 1:close_paren].strip()
        name_match = re.search(r"([A-Za-z_$][\w$]*)$", before)
        if not name_match:
            return
        name = name_match.group(1)
        modifiers = before[:name_match.start()].strip()
        visibility = self._java_visibility(modifiers, info.kind)
        if not self.include_private and visibility in {"-", "#"}:
            return

        # Return type: drop modifiers, then a leading method type-parameter list <T>.
        ret = " ".join(_JAVA_MODIFIERS.sub(" ", modifiers).split())
        if ret.startswith("<"):
            depth = 0
            for idx, ch in enumerate(ret):
                if ch == "<":
                    depth += 1
                elif ch == ">":
                    depth -= 1
                    if depth == 0:
                        ret = ret[idx + 1:].strip()
                        break
        is_constructor = name == info.name
        return_type = "" if is_constructor else (ret or "")

        params = self._format_java_parameters(params_text)
        info.methods.append(MethodInfo(
            name=name,
            visibility=visibility,
            parameters=params,
            return_type=return_type,
            is_static=bool(re.search(r"\bstatic\b", modifiers)),
            is_abstract=bool(re.search(r"\babstract\b", modifiers)) or (info.kind == "interface" and not body.strip() and not re.search(r"\b(default|static)\b", modifiers)),
        ))

        for param in params:
            info.used_types.update(self._type_names_from_display_signature(param))
        info.used_types.update(self._type_names(return_type))

        param_names = {p.split(":", 1)[0].strip() for p in params}
        for m in re.finditer(rf"(?:\bthis\s*\.\s*|(?<![\w$.]))([A-Za-z_$][\w$]*)\s*=(?!=)\s*new\s+({_QUALIFIED})", body):
            field_name, target = m.group(1), self._java_type_name(m.group(2))
            explicit = "this" in m.group(0).split(field_name)[0]
            info.pending.append(("composition", field_name, target, explicit))
        for m in re.finditer(r"\bthis\s*\.\s*([A-Za-z_$][\w$]*)\s*=\s*([A-Za-z_$][\w$]*)\s*;", body):
            if m.group(2) in param_names:
                info.pending.append(("aggregation", m.group(1), "", True))
        for m in re.finditer(rf"\bnew\s+({_QUALIFIED})", body):
            target = self._java_type_name(m.group(1))
            if target not in self.ignored_types:
                info.used_types.add(target)

    def _format_java_parameters(self, params_text: str) -> list[str]:
        if not params_text.strip():
            return []
        result: list[str] = []
        for raw in self._split_java_top_level(params_text):
            part = _JAVA_ANNOTATION.sub(" ", raw)
            part = re.sub(r"\b(final|volatile|transient)\b", " ", part)
            part = " ".join(part.split())
            if not part:
                continue
            match = re.match(r"(.+?)\s+([A-Za-z_$][\w$]*)$", part)
            if not match:
                result.append(part)
                continue
            type_name, name = match.groups()
            result.append(f"{name}: {self._java_type_name(type_name)}")
        return result


# --------------------------------------------------------------------------- #
# Class box model (text content + size)
# --------------------------------------------------------------------------- #

@dataclass
class ClassModel:
    info: ClassInfo
    title: str
    stereotype: str
    attr_lines: list[str]
    method_lines: list[str]
    width: float
    height: float
    header_h: float
    attr_h: float
    method_h: float


def _clip(text: str, size: int = MAX_CHARS) -> str:
    return text if len(text) <= size else text[: size - 1] + "…"


def field_line(f: FieldInfo) -> str:
    if f.source == "enum":
        return _clip(f"{f.visibility} {f.name}" + (f" = {f.default}" if f.default else ""))
    text = f"{f.visibility} {f.name}"
    if f.type_name:
        text += f": {f.type_name}"
    if f.default and f.source == "class":
        text += f" = {f.default}"
    return _clip(text)


def method_lines(m: MethodInfo) -> list[str]:
    modifiers = []
    if m.is_abstract:
        modifiers.append("abstract")
    if m.is_static:
        modifiers.append("static")
    if m.is_classmethod:
        modifiers.append("classmethod")
    if m.is_property:
        modifiers.append("property")
    if m.is_async:
        modifiers.append("async")
    mod_text = f"«{', '.join(modifiers)}» " if modifiers else ""
    head = f"{m.visibility} {mod_text}{m.name}"
    ret = f": {m.return_type}" if m.return_type else ""

    single = f"{head}({', '.join(m.parameters)}){ret}"
    if len(single) <= MAX_CHARS or not m.parameters:
        return [_clip(single)]

    # Long signature (typically a constructor with many parameters): one parameter per line.
    lines = [_clip(f"{head}(")]
    last = len(m.parameters) - 1
    for idx, param in enumerate(m.parameters):
        lines.append(_clip("    " + param + ("," if idx < last else "")))
    lines.append(_clip("  )" + ret))
    return lines


def build_model(info: ClassInfo) -> ClassModel:
    stereotypes: list[str] = []
    if info.kind != "class":
        stereotypes.append(info.kind)
    if info.is_abstract and info.kind == "class":
        stereotypes.append("abstract")
    stereotypes.extend(info.extra_stereotypes)
    stereotype = f"«{', '.join(stereotypes)}»" if stereotypes else ""

    attr_lines = [field_line(f) for f in info.fields]
    method_ls = [line for m in info.methods for line in method_lines(m)]

    text_width = max((len(line) for line in attr_lines + method_ls), default=0) * CHAR_WIDTH
    title_width = len(info.name) * TITLE_FONT_SIZE * 0.62
    width = math.ceil(max(BOX_MIN_WIDTH, 2 * PAD_X + text_width, 2 * PAD_X + title_width))

    header_h = PAD_Y + (STEREOTYPE_FONT_SIZE * 1.25 + 2 if stereotype else 0) + TITLE_FONT_SIZE * 1.25 + PAD_Y
    attr_h = 2 * PAD_Y + (len(attr_lines) * LINE_HEIGHT if attr_lines else 6)
    method_h = 2 * PAD_Y + (len(method_ls) * LINE_HEIGHT if method_ls else 6)
    return ClassModel(
        info=info, title=info.name, stereotype=stereotype,
        attr_lines=attr_lines, method_lines=method_ls,
        width=width, height=math.ceil(header_h + attr_h + method_h),
        header_h=header_h, attr_h=attr_h, method_h=method_h,
    )


# --------------------------------------------------------------------------- #
# Layout and edge routing
# --------------------------------------------------------------------------- #

@dataclass
class Box:
    name: str
    width: float
    height: float
    x: float = 0.0
    y: float = 0.0
    row: int = 0
    col: int = 0

    @property
    def cx(self) -> float:
        return self.x + self.width / 2

    @property
    def cy(self) -> float:
        return self.y + self.height / 2


@dataclass
class EdgePath:
    relation: Relation
    points: list[tuple[float, float]]


@dataclass
class Block:
    boxes: dict[str, Box]
    edges: list[EdgePath]
    width: float
    height: float


class DiagramLayout:
    """Layered layout (Sugiyama-style) with orthogonal, lane-routed edges."""

    def __init__(self, models: dict[str, ClassModel], relations: list[Relation], max_row_width: float):
        self.models = models
        self.relations = [r for r in relations if r.source in models and r.target in models and r.source != r.target]
        self.max_row_width = max_row_width

    # ------------------------------------------------------------------ main

    def run(self) -> tuple[dict[str, Box], list[EdgePath], float, float]:
        adjacency: dict[str, set[str]] = {n: set() for n in self.models}
        for r in self.relations:
            adjacency[r.source].add(r.target)
            adjacency[r.target].add(r.source)

        components = self._components(adjacency)
        blocks: list[Block] = []
        singles: list[str] = []
        for comp in components:
            if len(comp) == 1:
                singles.append(comp[0])
            else:
                blocks.append(self._layout_component(comp, adjacency))
        if singles:
            blocks.append(self._grid_block(singles))

        blocks.sort(key=lambda b: (-(b.width * b.height), -b.height))
        limit = max(self.max_row_width, max((b.width for b in blocks), default=0))

        boxes: dict[str, Box] = {}
        edges: list[EdgePath] = []
        cursor_x = cursor_y = 0.0
        row_h = 0.0
        max_right = max_bottom = 0.0
        for block in blocks:
            if cursor_x > 0 and cursor_x + block.width > limit:
                cursor_x = 0.0
                cursor_y += row_h + BLOCK_GAP
                row_h = 0.0
            dx, dy = CANVAS_MARGIN + cursor_x, CANVAS_MARGIN + cursor_y
            for name, box in block.boxes.items():
                box.x += dx
                box.y += dy
                boxes[name] = box
            for edge in block.edges:
                edge.points = [(px + dx, py + dy) for px, py in edge.points]
                edges.append(edge)
            cursor_x += block.width + BLOCK_GAP
            row_h = max(row_h, block.height)
            max_right = max(max_right, dx + block.width)
            max_bottom = max(max_bottom, dy + block.height)

        return boxes, edges, max_right + CANVAS_MARGIN, max_bottom + CANVAS_MARGIN

    def _new_box(self, name: str) -> Box:
        m = self.models[name]
        return Box(name, m.width, m.height)

    @staticmethod
    def _components(adjacency: dict[str, set[str]]) -> list[list[str]]:
        seen: set[str] = set()
        result: list[list[str]] = []
        for start in sorted(adjacency, key=str.lower):
            if start in seen:
                continue
            stack, comp = [start], []
            seen.add(start)
            while stack:
                node = stack.pop()
                comp.append(node)
                for nxt in adjacency[node]:
                    if nxt not in seen:
                        seen.add(nxt)
                        stack.append(nxt)
            result.append(sorted(comp, key=str.lower))
        return result

    # ------------------------------------------------------ isolated classes

    def _grid_block(self, names: list[str]) -> Block:
        names = sorted(names, key=lambda n: (self.models[n].info.module.lower(), self.models[n].title.lower()))
        boxes = {n: self._new_box(n) for n in names}
        limit = self.max_row_width
        x = y = 0.0
        row_h = 0.0
        max_w = 0.0
        for n in names:
            b = boxes[n]
            if x > 0 and x + b.width > limit:
                x = 0.0
                y += row_h + 50
                row_h = 0.0
            b.x, b.y = x, y
            x += b.width + HORIZONTAL_GAP
            row_h = max(row_h, b.height)
            max_w = max(max_w, b.x + b.width)
        return Block(boxes, [], max_w, y + row_h)

    # ------------------------------------------------------ connected layout

    @staticmethod
    def _break_cycles(nodes, down, up):
        color = dict.fromkeys(nodes, 0)
        kept: dict[str, set[str]] = {n: set() for n in nodes}
        order: dict[str, int] = {}
        roots = sorted((n for n in nodes if not up[n]), key=str.lower) + \
            sorted((n for n in nodes if up[n]), key=str.lower)
        for root in roots:
            if color[root]:
                continue
            color[root] = 1
            order[root] = len(order)
            stack = [(root, iter(sorted(down[root], key=str.lower)))]
            while stack:
                node, it = stack[-1]
                advanced = False
                for nxt in it:
                    if color[nxt] == 1:
                        continue  # back edge: drop it from the layering graph
                    kept[node].add(nxt)
                    if color[nxt] == 0:
                        color[nxt] = 1
                        order[nxt] = len(order)
                        stack.append((nxt, iter(sorted(down[nxt], key=str.lower))))
                        advanced = True
                        break
                if not advanced:
                    color[node] = 2
                    stack.pop()
        return kept, order

    def _layout_component(self, nodes: list[str], adjacency: dict[str, set[str]]) -> Block:
        node_set = set(nodes)
        rels = [r for r in self.relations if r.source in node_set and r.target in node_set]

        down: dict[str, set[str]] = {n: set() for n in nodes}
        up: dict[str, set[str]] = {n: set() for n in nodes}
        for r in rels:
            upper, lower = (r.target, r.source) if r.kind in HIERARCHY_KINDS else (r.source, r.target)
            down[upper].add(lower)
            up[lower].add(upper)

        kept, discovery = self._break_cycles(nodes, down, up)

        # Longest-path layering.
        indegree = dict.fromkeys(nodes, 0)
        for u in kept:
            for v in kept[u]:
                indegree[v] += 1
        queue = sorted((n for n in nodes if indegree[n] == 0), key=str.lower)
        layer = dict.fromkeys(nodes, 0)
        topo: list[str] = []
        while queue:
            u = queue.pop(0)
            topo.append(u)
            for v in sorted(kept[u], key=str.lower):
                layer[v] = max(layer[v], layer[u] + 1)
                indegree[v] -= 1
                if indegree[v] == 0:
                    queue.append(v)
        kept_up: dict[str, set[str]] = {n: set() for n in nodes}
        for u in kept:
            for v in kept[u]:
                kept_up[v].add(u)
        for u in reversed(topo):  # pull roots down next to their children
            if not kept_up[u] and kept[u]:
                layer[u] = min(layer[v] for v in kept[u]) - 1

        depth = max(layer.values()) + 1
        layers: list[list[str]] = [[] for _ in range(depth)]
        for n in sorted(nodes, key=lambda n: (layer[n], discovery.get(n, 0))):
            layers[layer[n]].append(n)
        layers = [l for l in layers if l]
        layer_of = {n: i for i, l in enumerate(layers) for n in l}

        self._order_layers(layers, layer_of, adjacency, node_set)

        # Wrap over-wide layers into several visual rows.
        boxes = {n: self._new_box(n) for n in nodes}
        rows: list[list[str]] = []
        for layer_nodes in layers:
            chunk: list[str] = []
            width = 0.0
            for n in layer_nodes:
                w = boxes[n].width
                if chunk and width + HORIZONTAL_GAP + w > self.max_row_width:
                    rows.append(chunk)
                    chunk, width = [], 0.0
                width += (HORIZONTAL_GAP if chunk else 0) + w
                chunk.append(n)
            if chunk:
                rows.append(chunk)
        for ri, row in enumerate(rows):
            for ci, n in enumerate(row):
                boxes[n].row, boxes[n].col = ri, ci

        self._place_rows(rows, boxes, adjacency, node_set)
        edges = self._route(rows, boxes, rels)

        max_x = max(b.x + b.width for b in boxes.values())
        max_y = max(b.y + b.height for b in boxes.values())
        return Block(boxes, edges, max_x, max_y)

    @staticmethod
    def _order_layers(layers, layer_of, adjacency, node_set) -> None:
        """Barycentre sweeps to reduce edge crossings."""
        def positions():
            return {n: (i + 0.5) / len(l) for l in layers for i, n in enumerate(l)}

        for _ in range(12):
            for direction in ("down", "up"):
                indices = range(1, len(layers)) if direction == "down" else range(len(layers) - 2, -1, -1)
                for li in indices:
                    pos = positions()

                    def key(n, li=li, direction=direction, pos=pos):
                        ns = [
                            pos[m] for m in adjacency[n]
                            if m in node_set and (layer_of[m] < li if direction == "down" else layer_of[m] > li)
                        ]
                        return sum(ns) / len(ns) if ns else pos[n]

                    layers[li].sort(key=key)

    @staticmethod
    def _resolve_row(row: list[str], boxes: dict[str, Box], desired: dict[str, float]) -> dict[str, float]:
        """Place boxes near their desired centres without overlapping; keeps the order."""
        n = len(row)
        left = [0.0] * n
        right = [0.0] * n
        prev_right = -math.inf
        for i, name in enumerate(row):
            x = desired[name] - boxes[name].width / 2
            if i:
                x = max(x, prev_right + HORIZONTAL_GAP)
            left[i] = x
            prev_right = x + boxes[name].width
        next_left = math.inf
        for i in range(n - 1, -1, -1):
            name = row[i]
            x = desired[name] - boxes[name].width / 2
            if i < n - 1:
                x = min(x, next_left - HORIZONTAL_GAP - boxes[name].width)
            right[i] = x
            next_left = x
        return {row[i]: (left[i] + right[i]) / 2 + boxes[row[i]].width / 2 for i in range(n)}

    def _place_rows(self, rows, boxes, adjacency, node_set) -> None:
        row_of = {n: ri for ri, row in enumerate(rows) for n in row}
        centers: dict[str, float] = {}
        for row in rows:
            total = sum(boxes[n].width for n in row) + HORIZONTAL_GAP * (len(row) - 1)
            x = -total / 2
            for n in row:
                centers[n] = x + boxes[n].width / 2
                x += boxes[n].width + HORIZONTAL_GAP

        def sweep(indices, above: bool) -> None:
            for ri in indices:
                row = rows[ri]
                desired = {}
                for n in row:
                    ns = [centers[m] for m in adjacency[n]
                          if m in node_set and (row_of[m] < ri if above else row_of[m] > ri)]
                    desired[n] = sum(ns) / len(ns) if ns else centers[n]
                centers.update(self._resolve_row(row, boxes, desired))

        for _ in range(10):
            sweep(range(1, len(rows)), above=True)
            sweep(range(len(rows) - 2, -1, -1), above=False)
        sweep(range(1, len(rows)), above=True)

        min_x = min(centers[n] - boxes[n].width / 2 for n in centers)
        for n, c in centers.items():
            boxes[n].x = c - boxes[n].width / 2 - min_x

    # ---------------------------------------------------------------- routing

    def _route(self, rows, boxes, rels) -> list[EdgePath]:
        n_rows = len(rows)

        def blockers(x: float, row_from: int, row_to: int) -> int:
            total = 0
            for ri in range(row_from + 1, row_to):
                for n in rows[ri]:
                    b = boxes[n]
                    if b.x - 10 <= x <= b.x + b.width + 10:
                        total += 1
            return total

        plans: list[dict] = []
        for r in rels:
            S, T = boxes[r.source], boxes[r.target]
            plan = {"rel": r, "S": S, "T": T, "gap": None, "fs": 0.5, "ft": 0.5, "lane": None}
            if S.row == T.row:
                if abs(S.col - T.col) == 1:
                    plan["kind"] = "side"
                    plan["ss"], plan["ts"] = ("right", "left") if T.col > S.col else ("left", "right")
                else:
                    plan["kind"] = "arch"
                    plan["ss"] = plan["ts"] = "top"
                    plan["gap"] = S.row
            else:
                plan["kind"] = "vertical"
                upper, lower = (S, T) if S.row < T.row else (T, S)
                if S.row < T.row:
                    plan["ss"], plan["ts"] = "bottom", "top"
                else:
                    plan["ss"], plan["ts"] = "top", "bottom"
                if lower.row == upper.row + 1:
                    plan["gap"] = lower.row
                else:
                    cost_a = blockers(lower.cx, upper.row, lower.row)   # lane just below the upper row
                    cost_b = blockers(upper.cx, upper.row, lower.row)   # lane just above the lower row
                    plan["gap"] = upper.row + 1 if cost_a <= cost_b else lower.row
            plans.append(plan)

        # Ports: spread the edge ends along each box side, ordered by the other end's position.
        ends: dict[tuple[str, str], list[tuple[int, str, float]]] = defaultdict(list)
        for i, p in enumerate(plans):
            S, T = p["S"], p["T"]
            for role, box, side, other in (("s", S, p["ss"], T), ("t", T, p["ts"], S)):
                key = other.cx if side in {"top", "bottom"} else other.cy
                ends[(box.name, side)].append((i, role, key))
        for (_, _), items in ends.items():
            items.sort(key=lambda it: it[2])
            for k, (i, role, _) in enumerate(items):
                plans[i]["f" + role] = (k + 1) / (len(items) + 1)

        # Lanes: interval partitioning per gap between rows.
        by_gap: dict[int, list[dict]] = defaultdict(list)
        for p in plans:
            if p["kind"] in {"vertical", "arch"}:
                sx = p["S"].x + p["fs"] * p["S"].width
                tx = p["T"].x + p["ft"] * p["T"].width
                p["span"] = (min(sx, tx), max(sx, tx))
                if abs(sx - tx) >= 1:
                    by_gap[p["gap"]].append(p)
        lanes_in_gap = [0] * (n_rows + 1)
        for gap, items in by_gap.items():
            items.sort(key=lambda p: (p["span"][0], p["span"][1]))
            lane_end: list[float] = []
            for p in items:
                for li, end in enumerate(lane_end):
                    if end + 10 < p["span"][0]:
                        lane_end[li] = p["span"][1]
                        p["lane"] = li
                        break
                else:
                    p["lane"] = len(lane_end)
                    lane_end.append(p["span"][1])
            lanes_in_gap[gap] = len(lane_end)

        # Vertical placement of the rows, leaving room for the lanes.
        gap_h = []
        for g in range(n_rows + 1):
            need = 40 + LANE_SPACING * lanes_in_gap[g]
            gap_h.append((need if lanes_in_gap[g] else 0) if g == 0 else max(BASE_VERTICAL_GAP, need))
        row_h = [max(boxes[n].height for n in row) for row in rows]
        row_y: list[float] = []
        y = gap_h[0]
        for ri in range(n_rows):
            row_y.append(y)
            y += row_h[ri] + (gap_h[ri + 1] if ri + 1 < n_rows else 0)
        for ri, row in enumerate(rows):
            for n in row:
                boxes[n].y = row_y[ri]

        def lane_y(gap: int, lane: int) -> float:
            top = (row_y[gap - 1] + row_h[gap - 1]) if gap > 0 else 0.0
            span = (lanes_in_gap[gap] - 1) * LANE_SPACING
            return top + (gap_h[gap] - span) / 2 + lane * LANE_SPACING

        # Final polylines.
        edges: list[EdgePath] = []
        for p in plans:
            S, T = p["S"], p["T"]

            def port(box: Box, side: str, f: float) -> tuple[float, float]:
                if side == "top":
                    return box.x + f * box.width, box.y
                if side == "bottom":
                    return box.x + f * box.width, box.y + box.height
                if side == "left":
                    return box.x, box.y + f * box.height
                return box.x + box.width, box.y + f * box.height

            a = port(S, p["ss"], p["fs"])
            b = port(T, p["ts"], p["ft"])
            if p["kind"] == "side":
                if abs(a[1] - b[1]) < 1:
                    pts = [a, b]
                else:
                    mid_x = (a[0] + b[0]) / 2
                    pts = [a, (mid_x, a[1]), (mid_x, b[1]), b]
            else:
                if p["lane"] is None:
                    pts = [a, b] if abs(a[0] - b[0]) < 1 else [a, (a[0], (a[1] + b[1]) / 2), (b[0], (a[1] + b[1]) / 2), b]
                else:
                    ly = lane_y(p["gap"], p["lane"])
                    pts = [a, (a[0], ly), (b[0], ly), b]
            edges.append(EdgePath(p["rel"], pts))
        return edges


# --------------------------------------------------------------------------- #
# Excalidraw scene
# --------------------------------------------------------------------------- #

class ExcalidrawBuilder:
    def __init__(self, models, boxes, edges):
        self.models = models
        self.boxes = boxes
        self.edges = edges
        self.elements: list[dict] = []
        self._counter = 0
        self.rect_ids: dict[str, str] = {}
        self.bound: dict[str, list[dict]] = defaultdict(list)

    def build(self) -> dict:
        for name in self.boxes:
            self.rect_ids[name] = self._id("class")
        self._add_edges()
        for name in sorted(self.boxes, key=str.lower):
            self._add_class(name)
        self._add_labels()
        return {
            "type": "excalidraw",
            "version": 2,
            "source": "https://excalidraw.com",
            "elements": self.elements,
            "appState": {"gridSize": 20, "viewBackgroundColor": "#ffffff"},
            "files": {},
        }

    # --------------------------------------------------------------- classes

    def _add_class(self, name: str) -> None:
        model, box = self.models[name], self.boxes[name]
        gid = self._id("group")
        rect = self._base(self.rect_ids[name], "rectangle", box.x, box.y, box.width, box.height,
                          background="#f7f7f7", roundness={"type": 3}, group=gid)
        rect["boundElements"] = self.bound[name]
        self.elements.append(rect)

        y_attr = box.y + model.header_h
        y_meth = y_attr + model.attr_h
        for y in (y_attr, y_meth):
            self.elements.append(self._base(self._id("line"), "line", box.x, y, box.width, 0,
                                            points=[[0, 0], [box.width, 0]], group=gid))

        ty = box.y + PAD_Y
        if model.stereotype:
            self.elements.append(self._text(box.x, ty, box.width, model.stereotype,
                                            STEREOTYPE_FONT_SIZE, "center", 1.25, gid))
            ty += STEREOTYPE_FONT_SIZE * 1.25 + 2
        self.elements.append(self._text(box.x, ty, box.width, model.title,
                                        TITLE_FONT_SIZE, "center", 1.25, gid))
        if model.attr_lines:
            self.elements.append(self._text(box.x + PAD_X, y_attr + PAD_Y, None, "\n".join(model.attr_lines),
                                            FONT_SIZE, "left", LINE_HEIGHT / FONT_SIZE, gid))
        if model.method_lines:
            self.elements.append(self._text(box.x + PAD_X, y_meth + PAD_Y, None, "\n".join(model.method_lines),
                                            FONT_SIZE, "left", LINE_HEIGHT / FONT_SIZE, gid))

    # ----------------------------------------------------------------- edges

    def _add_edges(self) -> None:
        self._labels: list[tuple[float, float, str]] = []
        for edge in self.edges:
            rel, pts = edge.relation, edge.points
            x0, y0 = pts[0]
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            arrow_id = self._id("rel")
            arrow = self._base(
                arrow_id, "arrow", x0, y0, max(xs) - min(xs), max(ys) - min(ys),
                points=[[px - x0, py - y0] for px, py in pts],
                stroke_style="dashed" if rel.kind in {"dependency", "realization"} else "solid",
            )
            start_head, end_head = {
                "inheritance": (None, "triangle_outline"),
                "realization": (None, "triangle_outline"),
                "composition": ("diamond", None),
                "aggregation": ("diamond_outline", None),
                "association": (None, "arrow"),
                "dependency": (None, "arrow"),
            }.get(rel.kind, (None, "arrow"))
            arrow["startArrowhead"], arrow["endArrowhead"] = start_head, end_head
            for key, (px, py), name in (("startBinding", pts[0], rel.source), ("endBinding", pts[-1], rel.target)):
                box = self.boxes[name]
                arrow[key] = {
                    "elementId": self.rect_ids[name],
                    "focus": 0,
                    "gap": 1,
                    "fixedPoint": [
                        round(min(1, max(0, (px - box.x) / box.width)), 4),
                        round(min(1, max(0, (py - box.y) / box.height)), 4),
                    ],
                    "mode": "orbit",
                }
                self.bound[name].append({"id": arrow_id, "type": "arrow"})
            self.elements.append(arrow)

            text = rel.label
            if rel.kind == "dependency" or not text:
                continue
            if rel.multiplicity:
                text += f" {rel.multiplicity}"
            segments = list(zip(pts, pts[1:]))
            (ax, ay), (bx, by) = max(segments, key=lambda s: abs(s[1][0] - s[0][0]) + abs(s[1][1] - s[0][1]))
            width = len(text) * LABEL_FONT_SIZE * 0.62
            if abs(by - ay) < 1:  # horizontal segment: label above the line
                self._labels.append(((ax + bx) / 2 - width / 2, ay - LABEL_FONT_SIZE * 1.25 - 3, text))
            else:                 # vertical segment: label at its right
                self._labels.append((ax + 6, (ay + by) / 2 - LABEL_FONT_SIZE * 0.6, text))

    def _add_labels(self) -> None:
        for x, y, text in self._labels:
            el = self._text(x, y, None, text, LABEL_FONT_SIZE, "left", 1.25, None)
            el["backgroundColor"] = "#ffffff"
            el["strokeColor"] = "#4b5563"
            self.elements.append(el)

    # --------------------------------------------------------------- helpers

    def _id(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}_{self._counter:05d}"

    def _base(self, element_id, kind, x, y, width, height, *, points=None, background="transparent",
              stroke_style="solid", roundness=None, group=None) -> dict:
        self._counter += 1
        element = {
            "id": element_id, "type": kind,
            "x": round(x, 2), "y": round(y, 2), "width": round(width, 2), "height": round(height, 2),
            "angle": 0, "strokeColor": "#1f2937", "backgroundColor": background,
            "fillStyle": "solid", "strokeWidth": 2, "strokeStyle": stroke_style,
            "roughness": 0, "opacity": 100,
            "groupIds": [group] if group else [], "frameId": None, "index": None,
            "roundness": roundness, "seed": 100000 + self._counter,
            "version": 1, "versionNonce": 100000 + self._counter * 97,
            "isDeleted": False, "boundElements": None, "updated": 1, "link": None, "locked": False,
        }
        if kind in {"line", "arrow"}:
            element["points"] = [[round(px, 2), round(py, 2)] for px, py in (points or [[0, 0], [width, height]])]
            element["lastCommittedPoint"] = None
            element["startBinding"] = None
            element["endBinding"] = None
            element["startArrowhead"] = None
            element["endArrowhead"] = None
        return element

    def _text(self, x, y, width, text, font_size, align, line_height, group) -> dict:
        lines = text.split("\n")
        natural = max(len(l) for l in lines) * font_size * (CHAR_WIDTH / FONT_SIZE)
        w = width if width is not None else natural
        h = len(lines) * font_size * line_height
        el = self._base(self._id("text"), "text", x, y, w, h, group=group)
        el.update({
            "text": text, "originalText": text, "fontSize": font_size, "fontFamily": 3,
            "textAlign": align, "verticalAlign": "top", "containerId": None,
            "autoResize": True, "lineHeight": round(line_height, 4), "baseline": font_size,
        })
        return el


# --------------------------------------------------------------------------- #
# SVG / PNG rendering
# --------------------------------------------------------------------------- #

class SvgRenderer:
    def __init__(self, scene: dict, width: float, height: float):
        self.scene = scene
        self.width = math.ceil(width)
        self.height = math.ceil(height)

    def render(self) -> str:
        out = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" height="{self.height}" '
            f'viewBox="0 0 {self.width} {self.height}">',
            '<rect width="100%" height="100%" fill="white"/>',
        ]
        for el in self.scene["elements"]:
            kind = el["type"]
            if kind == "rectangle":
                fill = el.get("backgroundColor", "transparent")
                out.append(
                    f'<rect x="{el["x"]}" y="{el["y"]}" width="{el["width"]}" height="{el["height"]}" rx="10" '
                    f'fill="{"none" if fill == "transparent" else fill}" stroke="{el["strokeColor"]}" stroke-width="2"/>'
                )
            elif kind in {"line", "arrow"}:
                out.extend(self._render_path(el))
            elif kind == "text":
                out.extend(self._render_text(el))
        out.append("</svg>")
        return "\n".join(out)

    @staticmethod
    def _render_path(el: dict) -> list[str]:
        pts = [(el["x"] + p[0], el["y"] + p[1]) for p in el["points"]]
        stroke = el["strokeColor"]
        dash = ' stroke-dasharray="8 6"' if el.get("strokeStyle") == "dashed" else ""
        d = "M " + " L ".join(f"{px:.2f} {py:.2f}" for px, py in pts)
        out = [f'<path d="{d}" fill="none" stroke="{stroke}" stroke-width="2"{dash} stroke-linejoin="miter"/>']
        if el["type"] != "arrow" or len(pts) < 2:
            return out

        def head(kind, tip, prev):
            dx, dy = tip[0] - prev[0], tip[1] - prev[1]
            length = math.hypot(dx, dy) or 1.0
            dx, dy = dx / length, dy / length
            nx, ny = -dy, dx
            tx, ty = tip

            def pt(back, side):
                return f"{tx - dx * back + nx * side:.2f},{ty - dy * back + ny * side:.2f}"

            if kind == "triangle_outline":
                return f'<polygon points="{pt(0, 0)} {pt(17, 9)} {pt(17, -9)}" fill="white" stroke="{stroke}" stroke-width="2"/>'
            if kind in {"diamond", "diamond_outline"}:
                fill = stroke if kind == "diamond" else "white"
                return (f'<polygon points="{pt(0, 0)} {pt(10, 6.5)} {pt(20, 0)} {pt(10, -6.5)}" '
                        f'fill="{fill}" stroke="{stroke}" stroke-width="2"/>')
            return f'<polyline points="{pt(13, 7)} {pt(0, 0)} {pt(13, -7)}" fill="none" stroke="{stroke}" stroke-width="2"/>'

        if el.get("endArrowhead"):
            out.append(head(el["endArrowhead"], pts[-1], pts[-2]))
        if el.get("startArrowhead"):
            out.append(head(el["startArrowhead"], pts[0], pts[1]))
        return out

    @staticmethod
    def _render_text(el: dict) -> list[str]:
        lines = el["text"].split("\n")
        fs = float(el["fontSize"])
        lh = fs * float(el.get("lineHeight", 1.25))
        x, y, w = float(el["x"]), float(el["y"]), float(el["width"])
        align = el.get("textAlign", "left")
        anchor = {"left": "start", "center": "middle", "right": "end"}[align]
        tx = x if anchor == "start" else (x + w / 2 if anchor == "middle" else x + w)
        out: list[str] = []
        bg = el.get("backgroundColor", "transparent")
        if bg != "transparent":
            out.append(f'<rect x="{x - 2}" y="{y - 1}" width="{w + 4}" height="{lh * len(lines) + 2}" fill="{bg}"/>')
        for i, line in enumerate(lines):
            baseline = y + i * lh + (lh - fs) / 2 + fs * 0.82
            safe = xml_escape(line).replace(" ", "\u00a0")  # keep indentation
            out.append(
                f'<text x="{tx:.2f}" y="{baseline:.2f}" font-family="{MONO_FONT}" font-size="{fs}" '
                f'fill="#111827" text-anchor="{anchor}">{safe}</text>'
            )
        return out


def export_png(svg_content: str, png_path: Path, width: float, height: float, scale: float) -> tuple[bool, str]:
    """Convert the in-memory SVG to PNG (no SVG file is left on disk)."""
    scale = max(0.25, min(scale, 20000 / max(width, height, 1)))
    try:
        import cairosvg  # type: ignore
        cairosvg.svg2png(bytestring=svg_content.encode("utf-8"), write_to=str(png_path), scale=scale)
        return True, "CairoSVG"
    except ImportError:
        pass
    except Exception as exc:
        return False, f"CairoSVG failed: {exc}"

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".svg", encoding="utf-8", delete=False) as temp:
            temp.write(svg_content)
            temp_path = Path(temp.name)

        converter = shutil.which("rsvg-convert")
        if converter:
            try:
                subprocess.run([converter, "-z", str(scale), str(temp_path), "-o", str(png_path)], check=True)
                return True, "rsvg-convert"
            except Exception as exc:
                return False, f"rsvg-convert failed: {exc}"

        converter = shutil.which("magick") or shutil.which("convert")
        if converter:
            try:
                subprocess.run([converter, "-density", str(int(96 * scale)), str(temp_path), str(png_path)], check=True)
                return True, Path(converter).name
            except Exception as exc:
                return False, f"ImageMagick failed: {exc}"

        return False, "CairoSVG, rsvg-convert and ImageMagick are all unavailable"
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return str(path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a UML class diagram (PNG + optional Excalidraw) from a Python/Java project."
    )
    parser.add_argument("project", nargs="?", type=Path, default=Path("."),
                        help="Project root directory (default: current directory)")
    parser.add_argument("-o", "--output", type=Path, default=None,
                        help="Output base path without extension, relative to the current directory "
                             "(default: ./uml_class_diagram)")
    parser.add_argument("--no-private", action="store_true", help="Hide private and protected members")
    parser.add_argument("--no-dependencies", action="store_true", help="Hide dependency arrows (less clutter)")
    parser.add_argument("--exclude", action="append", default=[], metavar="PATTERN",
                        help="Glob pattern relative to the project to exclude; repeatable. "
                             "E.g. 'tests/*' or '**/test_*.py'")
    parser.add_argument("--ignore-class", action="append", default=None, metavar="NAME",
                        help="Java class name to omit; repeatable (default: Main)")
    parser.add_argument("--ignore-type", action="append", default=None, metavar="NAME",
                        help="Java type whose console-style fields are omitted; repeatable (default: Scanner)")
    parser.add_argument("--max-width", type=int, default=DEFAULT_MAX_ROW_WIDTH,
                        help=f"Maximum layout row width in pixels (default: {DEFAULT_MAX_ROW_WIDTH})")
    parser.add_argument("--scale", type=float, default=2.0, help="PNG scale factor (default: 2.0)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--excalidraw", dest="excalidraw", action="store_const", const=True, default=None,
                       help="Always write the .excalidraw file (no prompt)")
    group.add_argument("--no-excalidraw", dest="excalidraw", action="store_const", const=False,
                       help="Never write the .excalidraw file (no prompt)")
    args = parser.parse_args()

    root = args.project.expanduser().resolve()
    if not root.is_dir():
        print(f"Error: directory does not exist: {root}", file=sys.stderr)
        return 2

    output = args.output.expanduser() if args.output else Path("uml_class_diagram")
    if not output.is_absolute():
        output = Path.cwd() / output
    if output.suffix.lower() in {".png", ".excalidraw"}:
        output = output.with_suffix("")
    output.parent.mkdir(parents=True, exist_ok=True)

    print(f"Analysing project: {display_path(root) if root != Path.cwd().resolve() else '.'}")
    analyzer = ProjectAnalyzer(
        root,
        include_private=not args.no_private,
        excluded_patterns=args.exclude,
        ignored_classes=set(args.ignore_class) if args.ignore_class is not None else None,
        ignored_types=set(args.ignore_type) if args.ignore_type is not None else None,
    )
    classes, relations = analyzer.analyze()
    if args.no_dependencies:
        relations = [r for r in relations if r.kind != "dependency"]

    print(f"  Files analysed : {len(analyzer.scanned_files)}")
    print(f"  Files ignored  : {len(analyzer.ignored_files)}")
    print(f"  Classes found  : {len(classes)}")
    print(f"  Relations      : {len(relations)}")
    if analyzer.errors:
        print(f"  Errors         : {len(analyzer.errors)}")
        for error in analyzer.errors:
            print(f"    - {error}")

    if not classes:
        print("\nNo Python/Java classes were found in the project.")
        return 1

    models = {q: build_model(info) for q, info in classes.items()}
    boxes, edges, width, height = DiagramLayout(models, relations, args.max_width).run()
    scene = ExcalidrawBuilder(models, boxes, edges).build()

    svg = SvgRenderer(scene, width, height).render()
    png_path = output.with_suffix(".png")
    ok, renderer = export_png(svg, png_path, width, height, args.scale)

    print("\nGenerated:")
    if ok:
        print(f"  PNG        : {display_path(png_path)} ({renderer})")
    else:
        print(f"  PNG        : NO ({renderer})")
        print("  To enable PNG output install one of:")
        print("    pip install cairosvg   (or: uv add cairosvg)")
        print("    rsvg-convert / ImageMagick (system package)")

    create_excalidraw = args.excalidraw
    if create_excalidraw is None:
        if sys.stdin.isatty():
            print()
            answer = input("Create the .excalidraw file? [Y/n]: ").strip().lower()
            create_excalidraw = answer in {"", "y", "yes", "s", "si", "sí"}
        else:
            create_excalidraw = True

    if create_excalidraw:
        excalidraw_path = output.with_suffix(".excalidraw")
        excalidraw_path.write_text(json.dumps(scene, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  Excalidraw : {display_path(excalidraw_path)}")
    else:
        print("  Excalidraw : not created")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

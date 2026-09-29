#!/usr/bin/env python3
"""
UML de clases -> Excalidraw + PNG

Analiza un proyecto Python/Java (sin ejecutar el proyecto) y genera:
    <salida>.png         -> imagen PNG
    <salida>.excalidraw  -> diagrama editable en Excalidraw (si el usuario lo confirma al final)

Uso:
    python uml_excalidraw.py /ruta/al/proyecto
    python uml_excalidraw.py /ruta/al/proyecto -o docs/uml

El análisis detecta, entre otras cosas:
- clases
- atributos de clase y atributos creados con self.x en métodos
- métodos, parámetros y retorno
- herencia
- asociaciones por anotaciones de tipos
- composición cuando self.x = Clase(...)
- dependencias por parámetros, retornos o uso de Clase(...)

No ejecuta código del proyecto; únicamente lo parsea con el AST de Python.
"""

from __future__ import annotations

import argparse
import ast
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from fnmatch import fnmatch
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape


IGNORE_DIRS = {
    ".git", ".hg", ".svn", ".venv", "venv", "env", "ENV",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "node_modules", "dist", "build", ".tox", ".idea", ".vscode",
    "site-packages",
}

IGNORE_JAVA_CLASSES = {
    "Main",
}

# Tipos de la biblioteca estándar que no queremos representar como dependencias UML.
IGNORE_JAVA_TYPES = {
    "Scanner",
}

BOX_MIN_WIDTH = 320
BOX_MAX_WIDTH = 520
CHAR_WIDTH = 9.0
LINE_HEIGHT = 24
HEADER_HEIGHT = 62
BODY_PADDING = 14
COMPARTMENT_GAP = 0
ATTR_BOTTOM_PADDING = 20
HORIZONTAL_GAP = 120
VERTICAL_GAP = 100
CANVAS_MARGIN = 80


@dataclass
class FieldInfo:
    name: str
    type_name: str = "Any"
    visibility: str = "+"
    default: str | None = None
    source: str = ""


@dataclass
class MethodInfo:
    name: str
    visibility: str
    parameters: list[str] = field(default_factory=list)
    return_type: str = "None"
    is_static: bool = False
    is_classmethod: bool = False
    is_property: bool = False
    is_async: bool = False


@dataclass
class ClassInfo:
    name: str
    module: str
    qualname: str
    file: str
    lineno: int
    bases: list[str] = field(default_factory=list)
    fields: list[FieldInfo] = field(default_factory=list)
    methods: list[MethodInfo] = field(default_factory=list)
    field_relations: list[tuple[str, str, str]] = field(default_factory=list)
    used_types: set[str] = field(default_factory=set)
    kind: str = "class"


@dataclass
class Relation:
    source: str
    target: str
    kind: str
    label: str = ""

    def priority(self) -> int:
        return {
            "inheritance": 100,
            "composition": 80,
            "aggregation": 70,
            "association": 60,
            "dependency": 40,
        }.get(self.kind, 0)


class ProjectAnalyzer:
    def __init__(
        self,
        root: Path,
        include_private: bool = True,
        excluded_patterns: list[str] | None = None,
    ):
        self.root = root.resolve()
        self.include_private = include_private
        self.script_path = Path(__file__).resolve()
        self.excluded_patterns = excluded_patterns or []
        self.classes: dict[str, ClassInfo] = {}
        self.short_name_to_qualified: dict[str, list[str]] = {}
        self.errors: list[str] = []
        self.scanned_files: list[str] = []
        self.ignored_files: list[str] = []

    def analyze(self) -> tuple[dict[str, ClassInfo], list[Relation]]:
        files = sorted(
            (p for p in self.root.rglob("*") if p.is_file() and p.suffix.lower() in {".py", ".java"}),
            key=lambda p: p.as_posix().lower(),
        )
        for path in files:
            if self._ignored(path):
                self.ignored_files.append(str(path.relative_to(self.root)))
                continue
            self.scanned_files.append(str(path.relative_to(self.root)))
            self._parse_file(path)

        self._build_name_index()
        relations = self._infer_relations()
        return self.classes, relations

    def _ignored(self, path: Path) -> bool:
        try:
            relative = path.relative_to(self.root)
        except ValueError:
            return True

        # Nunca analizar el propio generador UML aunque esté dentro del proyecto.
        # Este era el motivo por el que aparecían ProjectAnalyzer, ExcalidrawBuilder, etc.
        try:
            if path.resolve() == self.script_path:
                return True
        except OSError:
            pass

        if any(part in IGNORE_DIRS for part in relative.parts):
            return True

        relative_text = relative.as_posix()
        if any(fnmatch(relative_text, pattern) for pattern in self.excluded_patterns):
            return True

        return False

    def _module_name(self, path: Path) -> str:
        rel = path.relative_to(self.root).with_suffix("")
        parts = list(rel.parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts) if parts else self.root.name

    def _parse_file(self, path: Path) -> None:
        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                source = path.read_text(encoding="utf-8-sig")
            except Exception as exc:
                self.errors.append(f"{path}: no se pudo leer ({exc})")
                return
        except Exception as exc:
            self.errors.append(f"{path}: no se pudo leer ({exc})")
            return

        if path.suffix.lower() == ".java":
            self._parse_java_file(path, source)
            return

        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            self.errors.append(f"{path}:{exc.lineno}: sintaxis no válida")
            return

        module = self._module_name(path)
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                self._extract_class(node, module, path, tree)

    @staticmethod
    def _mask_java_source(source: str) -> str:
        """Oculta comentarios y literales para que el escaneo estructural no confunda llaves/paréntesis."""
        pattern = re.compile(
            r'//[^\n]*|/\*[\s\S]*?\*/|"""[\s\S]*?"""|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
            re.MULTILINE,
        )

        def repl(match: re.Match[str]) -> str:
            value = match.group(0)
            return "".join("\n" if ch == "\n" else " " for ch in value)

        return pattern.sub(repl, source)

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
    def _split_java_top_level(text: str, delimiter: str = ",") -> list[str]:
        result: list[str] = []
        start = 0
        paren = bracket = brace = angle = 0
        for i, ch in enumerate(text):
            if ch == "(":
                paren += 1
            elif ch == ")":
                paren = max(0, paren - 1)
            elif ch == "[":
                bracket += 1
            elif ch == "]":
                bracket = max(0, bracket - 1)
            elif ch == "{":
                brace += 1
            elif ch == "}":
                brace = max(0, brace - 1)
            elif ch == "<":
                angle += 1
            elif ch == ">" and angle:
                angle -= 1
            elif ch == delimiter and paren == bracket == brace == angle == 0:
                result.append(text[start:i].strip())
                start = i + 1
        tail = text[start:].strip()
        if tail:
            result.append(tail)
        return result

    @staticmethod
    def _java_strip_annotations(text: str) -> str:
        text = re.sub(r'@[A-Za-z_$][\w$]*(?:\s*\([^)]*\))?\s*', ' ', text)
        return " ".join(text.split())

    @staticmethod
    def _java_visibility(text: str, name: str = "") -> str:
        if re.search(r'\bprivate\b', text):
            return "-"
        if re.search(r'\bprotected\b', text):
            return "#"
        if re.search(r'\bpublic\b', text):
            return "+"
        return "~"

    @staticmethod
    def _java_type_name(type_text: str) -> str:
        type_text = ProjectAnalyzer._java_strip_annotations(type_text)
        type_text = re.sub(r'\b(final|volatile|transient|static|public|protected|private|abstract|native|synchronized|strictfp|default)\b', ' ', type_text)
        type_text = " ".join(type_text.replace("...", "[]").split())
        return type_text.strip()

    def _parse_java_file(self, path: Path, source: str) -> None:
        masked = self._mask_java_source(source)
        package_match = re.search(r'\bpackage\s+([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\s*;', masked)
        package = package_match.group(1) if package_match else path.stem

        declaration_pattern = re.compile(r'\b(class|interface|enum|record)\s+([A-Za-z_$][\w$]*)')
        declarations: list[dict] = []
        for match in declaration_pattern.finditer(masked):
            open_index = masked.find("{", match.end())
            if open_index < 0:
                continue
            close_index = self._find_matching_brace(masked, open_index)
            if close_index < 0:
                self.errors.append(f"{path}:{source.count(chr(10), 0, match.start()) + 1}: llaves no balanceadas")
                continue
            header = masked[match.end():open_index].strip()
            declarations.append({
                "kind": match.group(1),
                "name": match.group(2),
                "header": header,
                "open": open_index,
                "close": close_index,
                "start": match.start(),
            })

        if not declarations:
            return

        # Excluir clases Java que no queremos representar en el UML.
        declarations = [
            decl
            for decl in declarations
            if not (decl["kind"] == "class" and decl["name"] in IGNORE_JAVA_CLASSES)
        ]

        if not declarations:
            return

        # Determina clases anidadas mediante el intervalo de llaves más pequeño que las contiene.
        for decl in declarations:
            parents = [
                other for other in declarations
                if other["open"] < decl["start"] < other["close"]
            ]
            parent = min(parents, key=lambda d: d["close"] - d["open"]) if parents else None
            decl["parent"] = parent

        spans_by_key: dict[tuple[int, int], str] = {}
        for decl in declarations:
            chain: list[str] = []
            parent = decl.get("parent")
            while parent is not None:
                chain.append(parent["name"])
                parent = parent.get("parent")
            chain.reverse()
            chain.append(decl["name"])
            qual_parts = ([package] if package else []) + chain
            qualname = ".".join(qual_parts)
            spans_by_key[(decl["open"], decl["close"])] = qualname
            info = ClassInfo(
                name=decl["name"],
                module=package,
                qualname=qualname,
                file=str(path.relative_to(self.root)),
                lineno=source.count("\n", 0, decl["start"]) + 1,
                kind=decl["kind"],
            )

            header = self._java_strip_annotations(decl["header"])
            # Eliminamos parámetros del record antes de buscar extends/implements.
            header_for_bases = re.sub(r'\([^()]*\)', ' ', header)
            ext_match = re.search(r'\bextends\s+(.+?)(?=\bimplements\b|$)', header_for_bases)
            impl_match = re.search(r'\bimplements\s+(.+)$', header_for_bases)
            bases: list[str] = []
            if ext_match:
                bases.extend(self._split_java_top_level(ext_match.group(1)))
            if impl_match:
                bases.extend(self._split_java_top_level(impl_match.group(1)))
            info.bases = [self._java_type_name(x) for x in bases if x.strip()]

            self._parse_java_members(info, source, masked, decl["open"] + 1, decl["close"])
            self.classes[qualname] = info

        # Se vuelven a indexar al final de todos los archivos; las relaciones se resuelven después.

    def _parse_java_members(self, info: ClassInfo, source: str, masked: str, start: int, end: int) -> None:
        i = start
        member_start = start
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
                if re.search(r'\b(class|interface|enum|record)\s+[A-Za-z_$][\w$]*', prefix):
                    i = close + 1
                    member_start = i
                    continue
                if "(" in prefix:
                    body = source[i + 1:close]
                    self._parse_java_method(info, source, prefix, body)
                # Bloque estático/de instancia: no es un método UML.
                i = close + 1
                member_start = i
                continue
            elif ch == ";" and paren == 0 and bracket == 0:
                prefix = source[member_start:i].strip()
                masked_prefix = masked[member_start:i].strip()
                # Una declaración con "=" es un campo inicializado, aunque
                # su valor contenga una llamada como Scanner(System.in).
                if "(" in masked_prefix and "=" not in masked_prefix:
                    self._parse_java_method(info, source, masked_prefix, "")
                elif prefix:
                    self._parse_java_fields(info, prefix)
                i += 1
                member_start = i
                continue
            i += 1

        # Detecta composiciones explícitas: this.x = new Clase(...)
        body_text = masked[start:end]
        for match in re.finditer(r'\bthis\.([A-Za-z_$][\w$]*)\s*=\s*new\s+([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)', body_text):
            field_name, target = match.groups()
            target = self._java_type_name(target)
            if not any(f.name == field_name for f in info.fields):
                info.fields.append(FieldInfo(field_name, target, self._java_visibility("private"), source="instance"))
            info.field_relations.append((field_name, target, "composition"))
            info.used_types.add(target)

        # Dependencias por creación de objetos dentro de la clase.
        for match in re.finditer(r'\bnew\s+([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)', body_text):
            target = self._java_type_name(match.group(1))
            if target not in IGNORE_JAVA_TYPES:
                info.used_types.add(target)

        info.fields.sort(key=lambda f: (f.name.lower(), f.name))
        info.methods.sort(key=lambda m: (m.name not in {"__init__", info.name}, m.name.lower()))

    def _parse_java_fields(self, info: ClassInfo, declaration: str) -> None:
        # La visibilidad debe calcularse ANTES de eliminar los modificadores.
        # De lo contrario `private`/`protected`/`public` desaparecen y todo
        # lo que sea package-private termina correctamente como `~`, pero
        # incluso los campos explícitamente privados podrían quedar como `~`.
        declaration = self._java_strip_annotations(declaration)
        visibility = self._java_visibility(declaration)

        declaration = re.sub(r'\b(static|final|transient|volatile|public|protected|private|abstract|synchronized|native|strictfp)\b', ' ', declaration)
        declaration = " ".join(declaration.split())
        if not declaration or declaration.startswith("return "):
            return

        parts = self._split_java_top_level(declaration)
        if not parts:
            return
        first = re.match(r'^(.+?)\s+([A-Za-z_$][\w$]*)\s*(?:=(.*))?$', parts[0], re.S)
        if not first:
            return
        type_name, first_name, first_default = first.groups()
        type_name = self._java_type_name(type_name)

        # No representar la inicialización estándar de entrada por consola.
        # Ejemplo: Scanner scanner = new Scanner(System.in);
        if (
            type_name == "Scanner"
            and first_default
            and re.search(r"\bnew\s+Scanner\s*\(", first_default)
        ):
            return

        for idx, part in enumerate(parts):
            if idx == 0:
                name, default = first_name, first_default
            else:
                m = re.match(r'^([A-Za-z_$][\w$]*)\s*(?:=(.*))?$', part, re.S)
                if not m:
                    continue
                name, default = m.groups()
            if not self.include_private and visibility in {"-", "#"}:
                continue
            field = FieldInfo(
                name=name,
                type_name=type_name or "Any",
                visibility=visibility,
                default=" ".join((default or "").split())[:35] or None,
                source="class",
            )
            info.fields.append(field)
            if default:
                nm = re.search(r'\bnew\s+([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)', default)
                if nm:
                    target = self._java_type_name(nm.group(1))
                    info.field_relations.append((name, target, "composition"))
                    info.used_types.add(target)
            for type_name_ref in self._type_names(type_name):
                if type_name_ref not in IGNORE_JAVA_TYPES:
                    info.used_types.add(type_name_ref)

    def _parse_java_method(self, info: ClassInfo, source: str, signature: str, body: str) -> None:
        signature = self._java_strip_annotations(signature)
        open_paren = signature.find("(")
        close_paren = signature.rfind(")")
        if open_paren < 0 or close_paren < open_paren:
            return
        before = " ".join(signature[:open_paren].split())
        params_text = signature[open_paren + 1:close_paren].strip()
        name_match = re.search(r'([A-Za-z_$][\w$]*)$', before)
        if not name_match:
            return
        name = name_match.group(1)
        modifiers = before[:name_match.start()].strip()
        visibility = self._java_visibility(modifiers, name)
        if not self.include_private and visibility in {"-", "#"}:
            return

        cleaned_mods = re.sub(r'<[^<>]*>', ' ', modifiers)
        cleaned_mods = re.sub(r'\b(public|protected|private|static|final|abstract|synchronized|native|strictfp|default|sealed|non-sealed|transient|volatile)\b', ' ', cleaned_mods)
        cleaned_mods = " ".join(cleaned_mods.split())
        # Los constructores no tienen tipo de retorno en UML.
        return_type = "" if name == info.name else (cleaned_mods or "Any")
        params = self._format_java_parameters(params_text)
        method = MethodInfo(
            name=name,
            visibility=visibility,
            parameters=params,
            return_type=return_type,
            is_static=bool(re.search(r'\bstatic\b', modifiers)),
        )
        info.methods.append(method)

        for param in params:
            for type_name in self._type_names_from_display_signature(param):
                info.used_types.add(type_name)
        for type_name in self._type_names(return_type):
            info.used_types.add(type_name)
        for match in re.finditer(r'\bnew\s+([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)', body):
            target = self._java_type_name(match.group(1))
            if target not in IGNORE_JAVA_TYPES:
                info.used_types.add(target)

    def _format_java_parameters(self, params_text: str) -> list[str]:
        if not params_text.strip():
            return []
        result: list[str] = []
        for raw in self._split_java_top_level(params_text):
            part = self._java_strip_annotations(raw)
            part = re.sub(r'\b(final|volatile|transient)\b', ' ', part)
            part = " ".join(part.split())
            if not part:
                continue
            match = re.match(r'(.+?)\s+([A-Za-z_$][\w$]*)$', part)
            if not match:
                # Caso raro: parámetro sin nombre reconocible.
                result.append(part)
                continue
            type_name, name = match.groups()
            type_name = self._java_type_name(type_name)
            result.append(f"{name}: {type_name}")
        return result

    def _extract_class(self, node: ast.ClassDef, module: str, path: Path, tree: ast.AST) -> None:
        qualname = f"{module}.{node.name}" if module else node.name
        info = ClassInfo(
            name=node.name,
            module=module,
            qualname=qualname,
            file=str(path.relative_to(self.root)),
            lineno=getattr(node, "lineno", 0),
        )

        info.bases = [self._expr_name(base) for base in node.bases if self._expr_name(base)]

        field_map: dict[str, FieldInfo] = {}
        method_nodes: list[ast.FunctionDef | ast.AsyncFunctionDef] = []

        # Atributos declarados directamente en el cuerpo de la clase.
        for stmt in node.body:
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                name = stmt.target.id
                if not self.include_private and name.startswith("_"):
                    continue
                field_map[name] = FieldInfo(
                    name=name,
                    type_name=self._format_annotation(stmt.annotation),
                    visibility=self._visibility(name),
                    default=self._safe_unparse(stmt.value) if stmt.value else None,
                    source="class",
                )
            elif isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Name):
                        name = target.id
                        if not self.include_private and name.startswith("_"):
                            continue
                        field_map.setdefault(
                            name,
                            FieldInfo(
                                name=name,
                                type_name=self._infer_value_type(stmt.value),
                                visibility=self._visibility(name),
                                default=self._safe_unparse(stmt.value),
                                source="class",
                            ),
                        )
            elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method_nodes.append(stmt)

        # Los self.x que aparecen en métodos se consideran atributos de instancia.
        for fn in method_nodes:
            for sub in ast.walk(fn):
                if isinstance(sub, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                    targets: list[ast.AST] = []
                    if isinstance(sub, ast.Assign):
                        targets.extend(sub.targets)
                    elif isinstance(sub, ast.AnnAssign):
                        targets.append(sub.target)
                    else:
                        targets.append(sub.target)
                    for target in targets:
                        if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self":
                            name = target.attr
                            if not self.include_private and name.startswith("_"):
                                continue
                            annotation = getattr(sub, "annotation", None)
                            value = getattr(sub, "value", None)
                            type_name = self._format_annotation(annotation) if annotation else self._infer_value_type(value)
                            if name not in field_map:
                                field_map[name] = FieldInfo(
                                    name=name,
                                    type_name=type_name or "Any",
                                    visibility=self._visibility(name),
                                    default=self._safe_unparse(value) if value else None,
                                    source="instance",
                                )
                            elif field_map[name].type_name in {"Any", "", "None"} and type_name:
                                field_map[name].type_name = type_name

                            constructed = self._called_class_name(value)
                            if constructed:
                                info.field_relations.append((name, constructed, "composition"))

                # También registramos tipos utilizados en firmas.
            method_info = self._method_info(fn)
            if method_info:
                info.methods.append(method_info)
                for name in self._names_from_method_signature(fn):
                    info.used_types.add(name)

            # Uso explícito de Clase(...) dentro del método.
            for sub in ast.walk(fn):
                if isinstance(sub, ast.Call):
                    called = self._called_class_name(sub.func)
                    if called:
                        info.used_types.add(called)

        info.fields = sorted(field_map.values(), key=lambda f: (f.name.lower(), f.name))
        info.methods.sort(key=lambda m: (m.name not in {"__init__", info.name}, m.name.lower()))
        self.classes[info.qualname] = info

    def _build_name_index(self) -> None:
        for qualname, info in self.classes.items():
            self.short_name_to_qualified.setdefault(info.name, []).append(qualname)

    def _resolve_internal(self, name: str, current_module: str) -> str | None:
        if not name:
            return None
        clean = name.split("[")[0]
        clean = clean.removeprefix("typing.")

        # Nombre cualificado exacto.
        if clean in self.classes:
            return clean

        short = clean.rsplit(".", 1)[-1]
        candidates = self.short_name_to_qualified.get(short, [])
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]
        same_module = [q for q in candidates if self.classes[q].module == current_module]
        if len(same_module) == 1:
            return same_module[0]
        return None

    def _infer_relations(self) -> list[Relation]:
        dedup: dict[tuple[str, str], Relation] = {}

        for qualname, info in self.classes.items():
            # Herencia.
            for base in info.bases:
                target = self._resolve_internal(base, info.module)
                if target and target != qualname:
                    self._merge_relation(dedup, Relation(qualname, target, "inheritance"))

            # Atributos tipados y composición por instanciación.
            for field_name, type_name, rel_kind in info.field_relations:
                target = self._resolve_internal(type_name, info.module)
                if target and target != qualname:
                    self._merge_relation(dedup, Relation(qualname, target, rel_kind, field_name))

            for field in info.fields:
                for type_name in self._type_names(field.type_name):
                    target = self._resolve_internal(type_name, info.module)
                    if target and target != qualname:
                        self._merge_relation(dedup, Relation(qualname, target, "association", field.name))

            # Parámetros y retornos -> dependencia.
            for method in info.methods:
                for param in method.parameters:
                    for type_name in self._type_names_from_display_signature(param):
                        target = self._resolve_internal(type_name, info.module)
                        if target and target != qualname:
                            self._merge_relation(dedup, Relation(qualname, target, "dependency", method.name))
                for type_name in self._type_names(method.return_type):
                    target = self._resolve_internal(type_name, info.module)
                    if target and target != qualname:
                        self._merge_relation(dedup, Relation(qualname, target, "dependency", method.name))

            # Uso de Clase(...) -> dependencia, salvo que ya exista una relación más fuerte.
            for used in info.used_types:
                target = self._resolve_internal(used, info.module)
                if target and target != qualname:
                    self._merge_relation(dedup, Relation(qualname, target, "dependency", ""))

        return sorted(dedup.values(), key=lambda r: (r.source, r.target, -r.priority(), r.kind))

    @staticmethod
    def _merge_relation(dedup: dict[tuple[str, str], Relation], new: Relation) -> None:
        key = (new.source, new.target)
        old = dedup.get(key)
        if old is None or new.priority() > old.priority():
            dedup[key] = new
        elif old.label == "" and new.label:
            old.label = new.label

    def _method_info(self, fn: ast.FunctionDef | ast.AsyncFunctionDef) -> MethodInfo | None:
        name = fn.name
        if not self.include_private and name.startswith("_") and not name.startswith("__"):
            return None

        decorators = {self._expr_name(d) for d in fn.decorator_list}
        is_static = "staticmethod" in decorators
        is_class = "classmethod" in decorators
        is_property = "property" in decorators

        params = self._format_parameters(fn.args)
        # __init__ es un constructor y no muestra tipo de retorno en UML.
        ret = "" if name == "__init__" else (self._format_annotation(fn.returns) if fn.returns else "None")
        if ret == "Any":
            ret = "Any"

        return MethodInfo(
            name=name,
            visibility=self._visibility(name),
            parameters=params,
            return_type=ret,
            is_static=is_static,
            is_classmethod=is_class,
            is_property=is_property,
            is_async=isinstance(fn, ast.AsyncFunctionDef),
        )

    def _format_parameters(self, args: ast.arguments) -> list[str]:
        regular = list(args.posonlyargs) + list(args.args)
        defaults = [None] * (len(regular) - len(args.defaults)) + list(args.defaults)
        result: list[str] = []

        for arg, default in zip(regular, defaults):
            if arg.arg in {"self", "cls"}:
                continue
            text = arg.arg
            if arg.annotation:
                text += f": {self._format_annotation(arg.annotation)}"
            if default is not None:
                value = self._safe_unparse(default)
                if value:
                    text += f" = {self._truncate(value, 28)}"
            result.append(text)

        if args.vararg:
            text = "*" + args.vararg.arg
            if args.vararg.annotation:
                text += f": {self._format_annotation(args.vararg.annotation)}"
            result.append(text)

        for arg, default in zip(args.kwonlyargs, args.kw_defaults):
            text = arg.arg
            if arg.annotation:
                text += f": {self._format_annotation(arg.annotation)}"
            if default is not None:
                value = self._safe_unparse(default)
                if value:
                    text += f" = {self._truncate(value, 28)}"
            result.append(text)

        if args.kwarg:
            text = "**" + args.kwarg.arg
            if args.kwarg.annotation:
                text += f": {self._format_annotation(args.kwarg.annotation)}"
            result.append(text)

        return result

    def _names_from_method_signature(self, fn: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
        names: set[str] = set()
        args = list(fn.args.posonlyargs) + list(fn.args.args) + list(fn.args.kwonlyargs)
        if fn.args.vararg:
            args.append(fn.args.vararg)
        if fn.args.kwarg:
            args.append(fn.args.kwarg)
        for arg in args:
            if arg.annotation:
                names.update(self._type_names(self._format_annotation(arg.annotation)))
        if fn.returns:
            names.update(self._type_names(self._format_annotation(fn.returns)))
        return names

    def _type_names_from_display_signature(self, text: str) -> set[str]:
        if ":" not in text:
            return set()
        typ = text.split(":", 1)[1].split("=", 1)[0].strip()
        return self._type_names(typ)

    @staticmethod
    def _type_names(type_text: str) -> set[str]:
        if not type_text:
            return set()
        # Heurística simple sobre la cadena ya descompilada: conserva identificadores.
        import re
        return set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_.]*\b", type_text))

    @staticmethod
    def _called_class_name(node: ast.AST | None) -> str | None:
        if isinstance(node, ast.Call):
            node = node.func
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return ProjectAnalyzer._expr_name(node)
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
            return "Any"
        try:
            return ProjectAnalyzer._truncate(ast.unparse(node), 42)
        except Exception:
            return "Any"

    @staticmethod
    def _infer_value_type(node: ast.AST | None) -> str:
        if node is None:
            return "Any"
        if isinstance(node, ast.Call):
            return ProjectAnalyzer._expr_name(node.func) or "Any"
        if isinstance(node, ast.Constant):
            return type(node.value).__name__
        if isinstance(node, (ast.List, ast.ListComp, ast.Set, ast.SetComp)):
            return "list"
        if isinstance(node, (ast.Dict, ast.DictComp)):
            return "dict"
        return "Any"

    @staticmethod
    def _safe_unparse(node: ast.AST | None) -> str | None:
        if node is None:
            return None
        try:
            return ProjectAnalyzer._truncate(ast.unparse(node), 35)
        except Exception:
            return None

    @staticmethod
    def _truncate(text: str, size: int) -> str:
        text = " ".join(text.split())
        return text if len(text) <= size else text[: size - 1] + "…"

    @staticmethod
    def _visibility(name: str) -> str:
        # En UML tratamos los métodos especiales como públicos; un constructor
        # (__init__) sigue apareciendo dentro del compartimento de métodos.
        if name.startswith("__") and name.endswith("__"):
            return "+"
        if name.startswith("__"):
            return "-"
        if name.startswith("_"):
            return "#"
        return "+"


class ExcalidrawBuilder:
    def __init__(self, classes: dict[str, ClassInfo], relations: list[Relation]):
        self.classes = classes
        self.relations = relations
        self.elements: list[dict] = []
        self.boxes: dict[str, dict] = {}
        self._counter = 0
        self.width = 1600
        self.height = 1000

    def build(self) -> dict:
        self._layout_boxes()
        # Relaciones primero: quedan visualmente detrás de las clases.
        self._add_relations()
        for qualname in sorted(self.classes):
            self._add_class_elements(self.classes[qualname])
        return {
            "type": "excalidraw",
            "version": 2,
            "source": "https://excalidraw.com",
            "elements": self.elements,
            "appState": {
                "gridSize": 20,
                "viewBackgroundColor": "#ffffff",
                "zoom": {"value": 1},
                "scrollX": 0,
                "scrollY": 0,
            },
            "files": {},
        }

    def _layout_boxes(self) -> None:
        infos = sorted(
            self.classes.values(),
            key=lambda c: (len(c.fields) + len(c.methods), c.name),
            reverse=True,
        )
        n = len(infos)
        if n == 0:
            self.width, self.height = 800, 500
            return

        columns = max(1, min(4, math.ceil(math.sqrt(n))))

        # Calculamos primero el tamaño real de cada caja según su contenido.
        sizes = {
            info.qualname: (self._box_width(info), self._box_height(info))
            for info in infos
        }

        # Repartimos las clases por columnas buscando equilibrar su altura total.
        col_heights = [CANVAS_MARGIN] * columns
        assignments: list[tuple[ClassInfo, int]] = []
        column_widths = [0.0] * columns

        for info in infos:
            col = min(range(columns), key=lambda i: col_heights[i])
            width, height = sizes[info.qualname]
            assignments.append((info, col))
            col_heights[col] += height + VERTICAL_GAP
            column_widths[col] = max(column_widths[col], width)

        # Cada columna usa su propio ancho máximo para evitar solapamientos.
        col_x: list[float] = []
        current_x = float(CANVAS_MARGIN)
        for col in range(columns):
            col_x.append(current_x)
            current_x += column_widths[col] + HORIZONTAL_GAP

        col_heights = [CANVAS_MARGIN] * columns
        max_right = 0.0
        max_bottom = 0.0

        for info, col in assignments:
            width, height = sizes[info.qualname]
            x = col_x[col]
            y = col_heights[col]
            self.boxes[info.qualname] = {
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "id": self._id("class"),
                "boundElements": [],
            }
            col_heights[col] = y + height + VERTICAL_GAP
            max_right = max(max_right, x + width)
            max_bottom = max(max_bottom, y + height)

        self.width = max_right + CANVAS_MARGIN
        self.height = max_bottom + CANVAS_MARGIN

    def _box_width(self, info: ClassInfo) -> float:
        lines = [info.name, f"module: {info.module}"]
        lines.extend(self._field_display(f) for f in info.fields)
        lines.extend(self._method_display(m) for m in info.methods)
        longest = max((len(line) for line in lines), default=20)

        # El ancho se adapta al contenido real; no hay un máximo rígido.
        # Esto evita que firmas largas, especialmente constructores Java, sobresalgan.
        return max(BOX_MIN_WIDTH, 2 * BODY_PADDING + longest * CHAR_WIDTH)

    @staticmethod
    def _box_height(info: ClassInfo) -> float:
        attr_count = max(1, len(info.fields))
        method_count = max(1, len(info.methods))
        return (
            HEADER_HEIGHT
            + BODY_PADDING
            + attr_count * LINE_HEIGHT
            + ATTR_BOTTOM_PADDING
            + method_count * LINE_HEIGHT
            + BODY_PADDING
        )

    def _add_class_elements(self, info: ClassInfo) -> None:
        box = self.boxes[info.qualname]
        rect_id = box["id"]
        bound = box["boundElements"]
        rect = self._base_element(
            rect_id,
            "rectangle",
            box["x"],
            box["y"],
            box["width"],
            box["height"],
            background="#f7f7f7",
            roundness={"type": 3},
        )
        rect["boundElements"] = bound
        self.elements.append(rect)

        # Separadores UML.
        y_header = box["y"] + HEADER_HEIGHT
        attr_lines = max(1, len(info.fields))
        y_attr = y_header + attr_lines * LINE_HEIGHT + ATTR_BOTTOM_PADDING
        self.elements.append(self._base_element(
            self._id("line"), "line", box["x"], y_header, box["width"], 0,
            points=[[0, 0], [box["width"], 0]],
        ))
        self.elements.append(self._base_element(
            self._id("line"), "line", box["x"], y_attr, box["width"], 0,
            points=[[0, 0], [box["width"], 0]],
        ))

        # Título.
        title = info.name
        if info.kind in {"interface", "enum", "record"}:
            title = f"«{info.kind}»\n{title}"
        text_id = self._id("text")
        text = self._text_element(
            text_id,
            box["x"] + 10,
            box["y"] + 9,
            box["width"] - 20,
            HEADER_HEIGHT - 10,
            title,
            font_size=18,
            align="center",
            vertical="middle",
            container_id=rect_id,
        )
        bound.append({"id": text_id, "type": "text"})
        self.elements.append(text)

        # Atributos.
        attr_y = y_header + 6
        if info.fields:
            for field in info.fields:
                self.elements.append(self._text_element(
                    self._id("text"),
                    box["x"] + BODY_PADDING,
                    attr_y,
                    box["width"] - 2 * BODY_PADDING,
                    LINE_HEIGHT,
                    self._field_display(field),
                    font_size=14,
                    align="left",
                ))
                attr_y += LINE_HEIGHT
        else:
            self.elements.append(self._text_element(
                self._id("text"), box["x"] + BODY_PADDING, attr_y,
                box["width"] - 2 * BODY_PADDING, LINE_HEIGHT,
                "(sin atributos)", font_size=13,
            ))

        # Métodos.
        method_y = y_attr + 6
        if info.methods:
            for method in info.methods:
                self.elements.append(self._text_element(
                    self._id("text"),
                    box["x"] + BODY_PADDING,
                    method_y,
                    box["width"] - 2 * BODY_PADDING,
                    LINE_HEIGHT,
                    self._method_display(method),
                    font_size=14,
                ))
                method_y += LINE_HEIGHT
        else:
            self.elements.append(self._text_element(
                self._id("text"), box["x"] + BODY_PADDING, method_y,
                box["width"] - 2 * BODY_PADDING, LINE_HEIGHT,
                "(sin métodos)", font_size=13,
            ))

    def _add_relations(self) -> None:
        for relation in self.relations:
            if relation.source not in self.boxes or relation.target not in self.boxes:
                continue
            source = self.boxes[relation.source]
            target = self.boxes[relation.target]
            start, end, start_fp, end_fp = self._connection_points(source, target)
            dx = end[0] - start[0]
            dy = end[1] - start[1]
            min_x = min(start[0], end[0])
            min_y = min(start[1], end[1])
            arrow_id = self._id("rel")
            arrow = self._base_element(
                arrow_id,
                "arrow",
                min_x,
                min_y,
                abs(dx),
                abs(dy),
                points=[[start[0] - min_x, start[1] - min_y], [end[0] - min_x, end[1] - min_y]],
                stroke_style="dashed" if relation.kind == "dependency" else "solid",
            )
            arrow["startBinding"] = {
                "elementId": source["id"],
                "focus": 0,
                "gap": 6,
                "fixedPoint": start_fp,
                "mode": "orbit",
            }
            arrow["endBinding"] = {
                "elementId": target["id"],
                "focus": 0,
                "gap": 6,
                "fixedPoint": end_fp,
                "mode": "orbit",
            }
            arrow["startArrowhead"] = "diamond" if relation.kind == "composition" else None
            arrow["endArrowhead"] = {
                "inheritance": "triangle",
                "association": "arrow",
                "dependency": "arrow",
                "aggregation": "diamond",
                "composition": None,
            }.get(relation.kind, "arrow")
            self.elements.append(arrow)
            source.setdefault("boundElements", []).append({"id": arrow_id, "type": "arrow"})
            target.setdefault("boundElements", []).append({"id": arrow_id, "type": "arrow"})

            if relation.label:
                mx = (start[0] + end[0]) / 2
                my = (start[1] + end[1]) / 2 - 10
                label_id = self._id("label")
                label = relation.label
                self.elements.append(self._text_element(
                    label_id, mx - 75, my - 10, 150, 20, label,
                    font_size=11, align="center",
                ))

    @staticmethod
    def _connection_points(source: dict, target: dict):
        sx = source["x"] + source["width"] / 2
        sy = source["y"] + source["height"] / 2
        tx = target["x"] + target["width"] / 2
        ty = target["y"] + target["height"] / 2
        dx = tx - sx
        dy = ty - sy

        if abs(dx) >= abs(dy):
            if dx >= 0:
                start = (source["x"] + source["width"], sy)
                end = (target["x"], ty)
                return start, end, [1, 0.5], [0, 0.5]
            start = (source["x"], sy)
            end = (target["x"] + target["width"], ty)
            return start, end, [0, 0.5], [1, 0.5]
        else:
            if dy >= 0:
                start = (sx, source["y"] + source["height"])
                end = (tx, target["y"])
                return start, end, [0.5, 1], [0.5, 0]
            start = (sx, source["y"])
            end = (tx, target["y"] + target["height"])
            return start, end, [0.5, 0], [0.5, 1]

    @staticmethod
    def _field_display(field: FieldInfo) -> str:
        default = f" = {field.default}" if field.default and field.source == "class" else ""
        return f"{field.visibility} {field.name}: {field.type_name}{default}"

    @staticmethod
    def _method_display(method: MethodInfo) -> str:
        prefix = method.visibility
        modifiers = []
        if method.is_static:
            modifiers.append("static")
        if method.is_classmethod:
            modifiers.append("classmethod")
        if method.is_property:
            modifiers.append("property")
        if method.is_async:
            modifiers.append("async")
        modifier_text = f"«{', '.join(modifiers)}» " if modifiers else ""
        params = ", ".join(method.parameters)
        signature = f"{prefix} {modifier_text}{method.name}({params})"
        return f"{signature}: {method.return_type}" if method.return_type else signature

    def _base_element(
        self,
        element_id: str,
        kind: str,
        x: float,
        y: float,
        width: float,
        height: float,
        *,
        points: list[list[float]] | None = None,
        background: str = "transparent",
        stroke_style: str = "solid",
        roundness: dict | None = None,
    ) -> dict:
        self._counter += 1
        element = {
            "id": element_id,
            "type": kind,
            "x": round(x, 2),
            "y": round(y, 2),
            "width": round(width, 2),
            "height": round(height, 2),
            "angle": 0,
            "strokeColor": "#1f2937",
            "backgroundColor": background,
            "fillStyle": "solid",
            "strokeWidth": 2,
            "strokeStyle": stroke_style,
            "roughness": 1,
            "opacity": 100,
            "groupIds": [],
            "frameId": None,
            "index": None,
            "roundness": roundness,
            "seed": 100000 + self._counter,
            "version": 1,
            "versionNonce": 100000 + self._counter * 97,
            "isDeleted": False,
            "boundElements": None,
            "updated": 1,
            "link": None,
            "locked": False,
        }
        if kind in {"line", "arrow"}:
            element["points"] = points or [[0, 0], [width, height]]
            element["lastCommittedPoint"] = None
            element["startBinding"] = None
            element["endBinding"] = None
            element["startArrowhead"] = None
            element["endArrowhead"] = None
        return element

    def _text_element(
        self,
        element_id: str,
        x: float,
        y: float,
        width: float,
        height: float,
        text: str,
        *,
        font_size: int = 14,
        align: str = "left",
        vertical: str = "middle",
        container_id: str | None = None,
    ) -> dict:
        el = self._base_element(element_id, "text", x, y, width, height)
        el.update({
            "text": text,
            "fontSize": font_size,
            "fontFamily": 3,
            "textAlign": align,
            "verticalAlign": vertical,
            "containerId": container_id,
            "originalText": text,
            "autoResize": False,
            "lineHeight": 1.25,
            "baseline": max(0, font_size),
        })
        return el

    def _id(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}_{self._counter:05d}"


class SvgRenderer:
    def __init__(self, scene: dict):
        self.scene = scene

    def render(self) -> str:
        elements = self.scene.get("elements", [])
        width = int(self.scene.get("appState", {}).get("canvasWidth", 1600))
        height = int(self.scene.get("appState", {}).get("canvasHeight", 1000))
        if elements:
            max_x = max((el.get("x", 0) + max(1, el.get("width", 0)) for el in elements), default=width)
            max_y = max((el.get("y", 0) + max(1, el.get("height", 0)) for el in elements), default=height)
            width = max(width, int(max_x + CANVAS_MARGIN))
            height = max(height, int(max_y + CANVAS_MARGIN))

        out = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}">',
            '<rect width="100%" height="100%" fill="white"/>',
            '<g fill="none" stroke="#1f2937" stroke-width="2">',
        ]

        # Líneas/cajas primero; textos después para que siempre queden encima.
        for el in elements:
            if el.get("type") not in {"rectangle", "line", "arrow"}:
                continue
            typ = el.get("type")
            x = float(el.get("x", 0))
            y = float(el.get("y", 0))
            w = float(el.get("width", 0))
            h = float(el.get("height", 0))
            stroke = el.get("strokeColor", "#1f2937")
            dash = ' stroke-dasharray="8 6"' if el.get("strokeStyle") == "dashed" else ""
            if typ == "rectangle":
                fill = el.get("backgroundColor", "transparent")
                fill_value = "none" if fill == "transparent" else fill
                out.append(
                    f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" '
                    f'fill="{fill_value}" stroke="{stroke}"{dash}/>'
                )
            else:
                pts = el.get("points") or [[0, 0], [w, h]]
                if len(pts) < 2:
                    continue
                coords = [(x + float(p[0]), y + float(p[1])) for p in pts]
                d = "M " + " L ".join(f"{px} {py}" for px, py in coords)
                start_marker = ""
                end_marker = ""
                if typ == "arrow":
                    if el.get("startArrowhead"):
                        marker_name = {
                            "diamond": "diamond",
                            "triangle": "triangle",
                            "arrow": "arrow",
                        }.get(el.get("startArrowhead"), "arrow")
                        start_marker = f' marker-start="url(#{marker_name})"'
                    if el.get("endArrowhead"):
                        marker_name = {
                            "diamond": "diamond",
                            "triangle": "triangle",
                            "arrow": "arrow",
                        }.get(el.get("endArrowhead"), "arrow")
                        end_marker = f' marker-end="url(#{marker_name})"'
                out.append(f'<path d="{d}" fill="none" stroke="{stroke}"{dash}{start_marker}{end_marker}/>')

        out.extend([
            '</g>',
            '<g font-family="monospace" fill="#111827">',
        ])

        for el in elements:
            if el.get("type") != "text":
                continue
            text = el.get("text", "")
            x = float(el.get("x", 0))
            y = float(el.get("y", 0))
            w = float(el.get("width", 100))
            h = float(el.get("height", 20))
            font_size = float(el.get("fontSize", 14))
            align = el.get("textAlign", "left")
            anchor = {"left": "start", "center": "middle", "right": "end"}.get(align, "start")
            tx = x if anchor == "start" else (x + w / 2 if anchor == "middle" else x + w)
            lines = text.split("\n")
            line_h = font_size * 1.25
            total_h = line_h * len(lines)
            vertical = el.get("verticalAlign", "middle")
            if vertical == "top":
                start_y = y + font_size
            elif vertical == "bottom":
                start_y = y + h - total_h + font_size
            else:
                start_y = y + (h - total_h) / 2 + font_size
            for i, line in enumerate(lines):
                out.append(
                    f'<text x="{tx}" y="{start_y + i * line_h}" font-size="{font_size}" '
                    f'text-anchor="{anchor}">{xml_escape(line)}</text>'
                )

        out.extend([
            '</g>',
            '<defs>',
            '<marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="5" orient="auto">'
            '<path d="M 0 0 L 10 5 L 0 10 z" fill="#1f2937"/></marker>',
            '<marker id="triangle" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto">'
            '<path d="M 0 0 L 12 6 L 0 12 Z" fill="white" stroke="#1f2937" stroke-width="1.5"/></marker>',
            '<marker id="diamond" markerWidth="14" markerHeight="14" refX="12" refY="7" orient="auto">'
            '<path d="M 0 7 L 7 0 L 14 7 L 7 14 Z" fill="#1f2937" stroke="#1f2937" stroke-width="1.2"/></marker>',
            '</defs>',
            '</svg>',
        ])
        return "\n".join(out)


def export_png(svg_content: str, png_path: Path) -> tuple[bool, str]:
    """Convierte el SVG generado en memoria a PNG sin dejar un archivo SVG en disco."""
    try:
        import cairosvg  # type: ignore
        cairosvg.svg2png(
            bytestring=svg_content.encode("utf-8"),
            write_to=str(png_path),
        )
        return True, "CairoSVG"
    except ImportError:
        pass
    except Exception as exc:
        return False, f"CairoSVG falló: {exc}"

    # Los conversores externos necesitan un archivo temporal; se elimina al terminar.
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".svg",
            encoding="utf-8",
            delete=False,
        ) as temp:
            temp.write(svg_content)
            temp_path = Path(temp.name)

        converter = shutil.which("rsvg-convert")
        if converter:
            try:
                subprocess.run(
                    [converter, str(temp_path), "-o", str(png_path)],
                    check=True,
                )
                return True, "rsvg-convert"
            except Exception as exc:
                return False, f"rsvg-convert falló: {exc}"

        converter = shutil.which("magick") or shutil.which("convert")
        if converter:
            try:
                subprocess.run(
                    [converter, str(temp_path), str(png_path)],
                    check=True,
                )
                return True, Path(converter).name
            except Exception as exc:
                return False, f"ImageMagick falló: {exc}"

        return False, "No hay CairoSVG, rsvg-convert ni ImageMagick disponibles"
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Genera UML de clases desde un proyecto Python/Java en Excalidraw + PNG."
    )
    parser.add_argument(
        "project",
        type=Path,
        help="Directorio raíz del proyecto (Python y/o Java)",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="Ruta base de salida (sin extensión)",
    )
    parser.add_argument(
        "--no-private",
        action="store_true",
        help="Oculta atributos/métodos privados y protegidos",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="PATRON",
        help="Patrón glob relativo al proyecto a excluir. Puede repetirse. Ej.: tests/* o **/test_*.py",
    )
    args = parser.parse_args()

    root = args.project.expanduser().resolve()
    if not root.is_dir():
        print(f"Error: no existe el directorio: {root}", file=sys.stderr)
        return 2

    output = args.output.expanduser() if args.output else root / "uml_class_diagram"
    if output.suffix:
        output = output.with_suffix("")
    output.parent.mkdir(parents=True, exist_ok=True)

    print(f"Analizando proyecto: {root}")
    analyzer = ProjectAnalyzer(
        root,
        include_private=not args.no_private,
        excluded_patterns=args.exclude,
    )
    classes, relations = analyzer.analyze()

    print(f"  Archivos analizados : {len(analyzer.scanned_files)}")
    print(f"  Archivos ignorados  : {len(analyzer.ignored_files)}")
    print(f"  Clases encontradas  : {len(classes)}")
    print(f"  Relaciones          : {len(relations)}")
    if analyzer.errors:
        print(f"  Errores              : {len(analyzer.errors)}")
        for error in analyzer.errors:
            print(f"    - {error}")

    if not classes:
        print("\nNo se encontraron clases Python/Java en el proyecto.")
        return 1

    builder = ExcalidrawBuilder(classes, relations)
    scene = builder.build()
    scene["appState"]["canvasWidth"] = builder.width
    scene["appState"]["canvasHeight"] = builder.height

    # El PNG se genera directamente desde la escena en memoria.
    svg = SvgRenderer(scene).render()
    png_path = output.with_suffix(".png")
    ok, renderer = export_png(svg, png_path)

    print("\nGenerado:")
    if ok:
        print(f"  PNG        : {png_path} ({renderer})")
    else:
        print(f"  PNG        : NO ({renderer})")
        print("  Para PNG instala una de estas opciones:")
        print("    uv add cairosvg")
        print("    o instala rsvg-convert / ImageMagick en el sistema")

    # El .excalidraw se guarda solamente si el usuario lo solicita al final.
    print()
    answer = input("¿Quieres crear el archivo .excalidraw? [S/n]: ").strip().lower()
    create_excalidraw = answer in {"", "s", "si", "sí", "y", "yes"}

    if create_excalidraw:
        excalidraw_path = output.with_suffix(".excalidraw")
        excalidraw_path.write_text(
            json.dumps(scene, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"  Excalidraw : {excalidraw_path}")
    else:
        print("  Excalidraw : no creado")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

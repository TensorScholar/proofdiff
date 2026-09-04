from __future__ import annotations

import ast
import hashlib
import json
import re
from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

ALLOWED_EDGE_CLASSES = frozenset(
    {
        "declared_semantic",
        "static_program",
        "dynamic_trace",
        "historical_evidence",
        "critical_invariant",
    }
)
USED_EDGE_CLASSES = frozenset({"declared_semantic", "static_program", "critical_invariant"})
RISK_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}
TOKEN_RE = re.compile(r"[a-z0-9]+")
MIN_PREFIX_MATCH = 5
POLICY_ID = "phase8b_gate_c_minimal_big_v1"
FRESH_CALIBRATION_STATES = frozenset({"fresh", "preregistered_full_run_verified"})


@dataclass(frozen=True, order=True)
class Edge:
    src: str
    dst: str
    edge_class: str
    provenance: str

    def __post_init__(self) -> None:
        if self.edge_class not in ALLOWED_EDGE_CLASSES:
            raise ValueError(f"unsupported edge class: {self.edge_class}")


@dataclass(frozen=True, order=True)
class ImportEvidence:
    module: str
    provenance: str


@dataclass(frozen=True)
class GraphBuild:
    nodes: tuple[str, ...]
    edges: tuple[Edge, ...]
    changed_nodes: tuple[str, ...]
    unresolved_changed_paths: tuple[str, ...]
    parse_failed_paths: tuple[str, ...]
    parse_failed_changed_paths: tuple[str, ...]
    unresolved_local_imports: tuple[str, ...]
    dynamic_import_uncertainty_sites: tuple[str, ...]
    python_files_total: int
    python_files_parsed: int
    graph_digest: str


@dataclass(frozen=True)
class BigResult:
    selected_ids: tuple[str, ...]
    review: bool
    reasons: tuple[str, ...]
    graph_digest: str
    selected_proofs: dict[str, dict[str, Any]]
    skip_proofs: dict[str, dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_ids": list(self.selected_ids),
            "review": self.review,
            "reasons": list(self.reasons),
            "graph_digest": self.graph_digest,
            "selected_proofs": self.selected_proofs,
            "skip_proofs": self.skip_proofs,
        }


def _normalize_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.lstrip("/")


def _file_node(path: str) -> str:
    return f"source:{_normalize_path(path)}"


def _behavior_node(behavior_id: str) -> str:
    return f"behavior:{behavior_id}"


def _tokens(value: str) -> set[str]:
    return set(TOKEN_RE.findall(value.lower().replace("_", " ").replace("-", " ")))


def _token_related(left: str, right: str) -> bool:
    if left == right:
        return True
    if min(len(left), len(right)) < MIN_PREFIX_MATCH:
        return False
    return left.startswith(right) or right.startswith(left)


def _concept_overlap(left: Iterable[str], right: Iterable[str]) -> set[tuple[str, str]]:
    matches: set[tuple[str, str]] = set()
    left_tokens = set(left)
    right_tokens = set(right)
    for left_token in left_tokens:
        for right_token in right_tokens:
            if _token_related(left_token, right_token):
                matches.add((left_token, right_token))
    return matches


def _path_concepts(path: str, symbols: Iterable[str]) -> set[str]:
    concepts = _tokens(path)
    for symbol in symbols:
        concepts.update(_tokens(symbol))
    return concepts


def _behavior_concepts(behavior: dict[str, Any]) -> set[str]:
    concepts: set[str] = set()
    for tag in behavior.get("surface_tags", []):
        if isinstance(tag, str):
            concepts.update(_tokens(tag))
    description = behavior.get("description")
    if isinstance(description, str):
        concepts.update(_tokens(description))
    return concepts


def _module_parts(path: str) -> tuple[str, ...] | None:
    normalized = _normalize_path(path)
    if not normalized.endswith(".py"):
        return None
    parts = list(PurePosixPath(normalized).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return tuple(parts) if parts else None


def _module_aliases(path: str) -> tuple[str, ...]:
    parts = _module_parts(path)
    if not parts:
        return ()
    aliases: list[str] = []
    for index in range(len(parts)):
        alias = ".".join(parts[index:])
        if alias:
            aliases.append(alias)
    return tuple(aliases)


def _module_candidates(paths: Iterable[str]) -> dict[str, tuple[str, ...]]:
    candidates: dict[str, set[str]] = defaultdict(set)
    for path in paths:
        for alias in _module_aliases(path):
            candidates[alias].add(path)
    return {alias: tuple(sorted(values)) for alias, values in sorted(candidates.items())}


def _local_package_roots(candidates: dict[str, tuple[str, ...]]) -> frozenset[str]:
    roots: set[str] = set()
    for alias in candidates:
        parts = alias.split(".")
        if len(parts) >= 2:
            roots.add(parts[0])
    return frozenset(roots)


def _resolve_relative_module(current_path: str, level: int, module: str | None) -> str | None:
    if level == 0:
        return module
    parts = _module_parts(current_path)
    if not parts:
        return module
    package = list(parts[:-1])
    remove = max(level - 1, 0)
    if remove > len(package):
        return None
    if remove:
        package = package[:-remove]
    if module:
        package.extend(module.split("."))
    return ".".join(package) if package else None


def _resolution_probes(module: str) -> tuple[str, ...]:
    parts = module.split(".")
    return tuple(".".join(parts[:end]) for end in range(len(parts), 0, -1))


def _resolve_module(
    module: str,
    candidates: dict[str, tuple[str, ...]],
    local_roots: frozenset[str],
) -> tuple[str | None, str]:
    for probe in _resolution_probes(module):
        values = candidates.get(probe)
        if values is None:
            continue
        if len(values) == 1:
            return values[0], "resolved"
        return None, f"ambiguous_local:{probe}"
    root = module.split(".", 1)[0]
    if root in local_roots:
        return None, f"missing_local:{module}"
    return None, "external_or_unknown"


def _top_level_symbols(tree: ast.AST) -> tuple[str, ...]:
    symbols: set[str] = set()
    if not isinstance(tree, ast.Module):
        return ()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.add(node.name)
            if isinstance(node, ast.ClassDef):
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        symbols.add(f"{node.name}.{child.name}")
                        symbols.add(child.name)
    return tuple(sorted(symbols))


def _dynamic_import_target(call: ast.Call) -> tuple[str | None, bool]:
    builtin_import = isinstance(call.func, ast.Name) and call.func.id == "__import__"
    importlib_import = (
        isinstance(call.func, ast.Attribute)
        and call.func.attr == "import_module"
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "importlib"
    )
    is_dynamic_import = builtin_import or importlib_import
    if not is_dynamic_import:
        return None, False
    if not call.args:
        return None, True
    first = call.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str) and first.value:
        return first.value, True
    return None, True


def _import_evidence(path: str, tree: ast.AST) -> tuple[tuple[ImportEvidence, ...], tuple[str, ...]]:
    imports: set[ImportEvidence] = set()
    dynamic_uncertainty: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(ImportEvidence(alias.name, f"python_import:{alias.name}"))
        elif isinstance(node, ast.ImportFrom):
            resolved = _resolve_relative_module(path, node.level, node.module)
            if resolved:
                imports.add(ImportEvidence(resolved, f"python_import:{resolved}"))
            for alias in node.names:
                if alias.name == "*" or not resolved:
                    continue
                imported_module = f"{resolved}.{alias.name}"
                imports.add(ImportEvidence(imported_module, f"python_import:{imported_module}"))
        elif isinstance(node, ast.Call):
            target, is_dynamic = _dynamic_import_target(node)
            if not is_dynamic:
                continue
            if target is not None and not target.startswith("."):
                imports.add(
                    ImportEvidence(
                        target,
                        f"python_dynamic_import_literal:{target}",
                    )
                )
            else:
                dynamic_uncertainty.add(f"{path}:{getattr(node, 'lineno', 0)}")
    return tuple(sorted(imports)), tuple(sorted(dynamic_uncertainty))


def _semantic_edges(
    *,
    source_symbols: dict[str, tuple[str, ...]],
    behaviors: list[dict[str, Any]],
) -> list[Edge]:
    edges: list[Edge] = []
    for path, symbols in sorted(source_symbols.items()):
        source_concepts = _path_concepts(path, symbols)
        if not source_concepts:
            continue
        for behavior in behaviors:
            behavior_id = str(behavior["behavior_id"])
            overlap = _concept_overlap(source_concepts, _behavior_concepts(behavior))
            if not overlap:
                continue
            pairs = ",".join(f"{left}~{right}" for left, right in sorted(overlap))
            edges.append(
                Edge(
                    src=_file_node(path),
                    dst=_behavior_node(behavior_id),
                    edge_class="declared_semantic",
                    provenance=f"deterministic_concept_overlap:{pairs}",
                )
            )
    return edges


def _validate_inputs(
    *,
    sources: dict[str, str],
    changed_paths: list[str],
    behaviors: list[dict[str, Any]],
) -> None:
    if not changed_paths or not any(_normalize_path(path) for path in changed_paths):
        raise ValueError("changed_paths must not be empty")

    normalized_paths = [_normalize_path(path) for path in sources]
    if len(normalized_paths) != len(set(normalized_paths)):
        raise ValueError("sources contain duplicate normalized paths")

    behavior_ids: list[str] = []
    for behavior in behaviors:
        behavior_id = behavior.get("behavior_id")
        if not isinstance(behavior_id, str) or not behavior_id:
            raise ValueError("behavior_id must be a non-empty string")
        behavior_ids.append(behavior_id)
        risk = behavior.get("risk")
        if risk not in RISK_RANK:
            raise ValueError(f"unsupported behavior risk: {risk!r}")
    duplicates = sorted({item for item in behavior_ids if behavior_ids.count(item) > 1})
    if duplicates:
        raise ValueError(f"duplicate behavior_id: {duplicates[0]}")


def build_graph(
    *,
    sources: dict[str, str],
    changed_paths: list[str],
    behaviors: list[dict[str, Any]],
) -> GraphBuild:
    _validate_inputs(sources=sources, changed_paths=changed_paths, behaviors=behaviors)

    normalized_sources = {
        _normalize_path(path): text for path, text in sources.items() if _normalize_path(path).endswith(".py")
    }
    normalized_changed = tuple(sorted({_normalize_path(path) for path in changed_paths}))
    module_candidates = _module_candidates(normalized_sources)
    local_roots = _local_package_roots(module_candidates)

    source_symbols: dict[str, tuple[str, ...]] = {}
    source_imports: dict[str, tuple[ImportEvidence, ...]] = {}
    parse_failures: set[str] = set()
    dynamic_uncertainty_sites: set[str] = set()
    for path, text in sorted(normalized_sources.items()):
        try:
            tree = ast.parse(text, filename=path)
        except (SyntaxError, ValueError):
            parse_failures.add(path)
            source_symbols[path] = ()
            source_imports[path] = ()
            continue
        source_symbols[path] = _top_level_symbols(tree)
        imports, dynamic_uncertainty = _import_evidence(path, tree)
        source_imports[path] = imports
        dynamic_uncertainty_sites.update(dynamic_uncertainty)

    nodes: set[str] = {_file_node(path) for path in normalized_sources}
    nodes.update(_behavior_node(str(behavior["behavior_id"])) for behavior in behaviors)
    nodes.add("policy:critical")

    edges: list[Edge] = []
    unresolved_local_imports: set[str] = set()
    for importer_path, imports in sorted(source_imports.items()):
        for evidence in imports:
            dependency_path, status = _resolve_module(evidence.module, module_candidates, local_roots)
            if dependency_path is None:
                if status.startswith(("ambiguous_local:", "missing_local:")):
                    unresolved_local_imports.add(f"{importer_path}:{evidence.module}:{status}")
                continue
            if dependency_path == importer_path:
                continue
            # Impact flows from a changed dependency to its consumer.
            edges.append(
                Edge(
                    src=_file_node(dependency_path),
                    dst=_file_node(importer_path),
                    edge_class="static_program",
                    provenance=evidence.provenance,
                )
            )

    edges.extend(_semantic_edges(source_symbols=source_symbols, behaviors=behaviors))

    for behavior in behaviors:
        if str(behavior.get("risk")) == "critical":
            edges.append(
                Edge(
                    src="policy:critical",
                    dst=_behavior_node(str(behavior["behavior_id"])),
                    edge_class="critical_invariant",
                    provenance="frozen_behavior_catalog:risk=critical",
                )
            )

    unique_edges = tuple(sorted(set(edges)))
    unresolved = tuple(sorted(path for path in normalized_changed if path not in normalized_sources))
    parse_failed_changed = tuple(sorted(path for path in normalized_changed if path in parse_failures))
    changed_nodes = tuple(sorted(_file_node(path) for path in normalized_changed if path in normalized_sources))

    canonical = {
        "nodes": sorted(nodes),
        "edges": [
            {
                "src": edge.src,
                "dst": edge.dst,
                "edge_class": edge.edge_class,
                "provenance": edge.provenance,
            }
            for edge in unique_edges
        ],
        "changed_nodes": list(changed_nodes),
        "unresolved_changed_paths": list(unresolved),
        "parse_failed_paths": sorted(parse_failures),
        "parse_failed_changed_paths": list(parse_failed_changed),
        "unresolved_local_imports": sorted(unresolved_local_imports),
        "dynamic_import_uncertainty_sites": sorted(dynamic_uncertainty_sites),
    }
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return GraphBuild(
        nodes=tuple(sorted(nodes)),
        edges=unique_edges,
        changed_nodes=changed_nodes,
        unresolved_changed_paths=unresolved,
        parse_failed_paths=tuple(sorted(parse_failures)),
        parse_failed_changed_paths=parse_failed_changed,
        unresolved_local_imports=tuple(sorted(unresolved_local_imports)),
        dynamic_import_uncertainty_sites=tuple(sorted(dynamic_uncertainty_sites)),
        python_files_total=len(normalized_sources),
        python_files_parsed=len(normalized_sources) - len(parse_failures),
        graph_digest=digest,
    )


def _adjacency(edges: Iterable[Edge]) -> dict[str, tuple[Edge, ...]]:
    grouped: dict[str, list[Edge]] = defaultdict(list)
    for edge in edges:
        grouped[edge.src].append(edge)
    return {src: tuple(sorted(values)) for src, values in grouped.items()}


def _shortest_paths(graph: GraphBuild) -> dict[str, tuple[Edge, ...]]:
    adjacency = _adjacency(graph.edges)
    queue: deque[str] = deque(graph.changed_nodes)
    paths: dict[str, tuple[Edge, ...]] = {node: () for node in graph.changed_nodes}
    while queue:
        node = queue.popleft()
        for edge in adjacency.get(node, ()):
            if edge.dst in paths:
                continue
            paths[edge.dst] = paths[node] + (edge,)
            queue.append(edge.dst)
    return paths


def _risk_at_least(behavior: dict[str, Any], threshold: str) -> bool:
    return RISK_RANK.get(str(behavior.get("risk")), 0) >= RISK_RANK[threshold]


def _selected_proof(
    *,
    behavior_id: str,
    path: tuple[Edge, ...] | None,
    graph: GraphBuild,
    selection_mode: str,
) -> dict[str, Any]:
    if selection_mode == "critical_policy":
        impact_path = ["policy:critical", _behavior_node(behavior_id)]
        edge_classes = ["critical_invariant"]
        edge_provenance = ["frozen_behavior_catalog:risk=critical"]
    elif selection_mode == "uncertainty_widening":
        impact_path = []
        edge_classes = []
        edge_provenance = []
    else:
        assert path is not None
        impact_path = [path[0].src, *(edge.dst for edge in path)] if path else []
        edge_classes = [edge.edge_class for edge in path]
        edge_provenance = [edge.provenance for edge in path]
    return {
        "triggering_change_nodes": list(graph.changed_nodes),
        "candidate_behavior_node": _behavior_node(behavior_id),
        "selection_mode": selection_mode,
        "impact_path": impact_path,
        "edge_classes": edge_classes,
        "edge_provenance": edge_provenance,
        "graph_digest": graph.graph_digest,
        "policy_attribution": POLICY_ID,
    }


def _skip_proof(
    *,
    behavior_id: str,
    graph: GraphBuild,
    paths: dict[str, tuple[Edge, ...]],
    calibration_freshness: str,
    review: bool,
) -> dict[str, Any]:
    reachable_sources = sorted(node for node in paths if node.startswith("source:"))
    return {
        "changed_source_nodes": list(graph.changed_nodes),
        "candidate_behavior_node": _behavior_node(behavior_id),
        "edge_classes_considered": sorted(USED_EDGE_CLASSES),
        "no_path_reason": "no_admissible_path_from_changed_source_to_behavior",
        "uncertainty_state": "review_required" if review else "bounded_static_analysis",
        "calibration_freshness": calibration_freshness,
        "policy_attribution": POLICY_ID,
        "graph_digest": graph.graph_digest,
        "reachable_source_nodes": reachable_sources,
        "unresolved_local_imports": list(graph.unresolved_local_imports),
        "dynamic_import_uncertainty_sites": list(graph.dynamic_import_uncertainty_sites),
        "analysis_scope": {
            "python_files_total": graph.python_files_total,
            "python_files_parsed": graph.python_files_parsed,
            "python_files_parse_failed": len(graph.parse_failed_paths),
        },
    }


def select_with_big(
    *,
    sources: dict[str, str],
    changed_paths: list[str],
    behaviors: list[dict[str, Any]],
    calibration_freshness: str = "not_yet_calibrated",
) -> BigResult:
    graph = build_graph(sources=sources, changed_paths=changed_paths, behaviors=behaviors)
    paths = _shortest_paths(graph)

    calibration_uncertain = calibration_freshness not in FRESH_CALIBRATION_STATES
    review = bool(
        graph.unresolved_changed_paths
        or graph.parse_failed_changed_paths
        or graph.unresolved_local_imports
        or graph.dynamic_import_uncertainty_sites
        or calibration_uncertain
    )
    reasons: list[str] = []
    if graph.unresolved_changed_paths:
        reasons.append(f"unresolved_changed_paths={len(graph.unresolved_changed_paths)}")
    if graph.parse_failed_changed_paths:
        reasons.append(f"parse_failed_changed_paths={len(graph.parse_failed_changed_paths)}")
    if graph.unresolved_local_imports:
        reasons.append(f"unresolved_local_imports={len(graph.unresolved_local_imports)}")
    if graph.dynamic_import_uncertainty_sites:
        reasons.append(f"dynamic_import_uncertainty={len(graph.dynamic_import_uncertainty_sites)}")
    if calibration_uncertain:
        reasons.append(f"calibration:{calibration_freshness}")

    selected: set[str] = set()
    selected_proofs: dict[str, dict[str, Any]] = {}
    for behavior in behaviors:
        behavior_id = str(behavior["behavior_id"])
        behavior_node = _behavior_node(behavior_id)
        critical = str(behavior.get("risk")) == "critical"
        impact_path = paths.get(behavior_node)
        if critical:
            selected.add(behavior_id)
            selected_proofs[behavior_id] = _selected_proof(
                behavior_id=behavior_id,
                path=None,
                graph=graph,
                selection_mode="critical_policy",
            )
        elif impact_path is not None:
            selected.add(behavior_id)
            selected_proofs[behavior_id] = _selected_proof(
                behavior_id=behavior_id,
                path=impact_path,
                graph=graph,
                selection_mode="impact_path",
            )

    if review:
        # Ambiguity may increase evidence or force REVIEW, never justify a smaller suite.
        for behavior in behaviors:
            if not _risk_at_least(behavior, "high"):
                continue
            behavior_id = str(behavior["behavior_id"])
            if behavior_id in selected:
                continue
            selected.add(behavior_id)
            selected_proofs[behavior_id] = _selected_proof(
                behavior_id=behavior_id,
                path=None,
                graph=graph,
                selection_mode="uncertainty_widening",
            )
        reasons.append("uncertainty:widen_high_critical")

    skip_proofs = {
        str(behavior["behavior_id"]): _skip_proof(
            behavior_id=str(behavior["behavior_id"]),
            graph=graph,
            paths=paths,
            calibration_freshness=calibration_freshness,
            review=review,
        )
        for behavior in behaviors
        if str(behavior["behavior_id"]) not in selected
    }

    return BigResult(
        selected_ids=tuple(sorted(selected)),
        review=review,
        reasons=tuple(reasons),
        graph_digest=graph.graph_digest,
        selected_proofs={key: selected_proofs[key] for key in sorted(selected_proofs)},
        skip_proofs={key: skip_proofs[key] for key in sorted(skip_proofs)},
    )

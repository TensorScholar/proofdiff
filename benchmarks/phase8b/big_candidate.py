from __future__ import annotations

import ast
import hashlib
import json
import re
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Iterable

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
POLICY_ID = "phase8b_gate_b_frozen_candidate_v1"


@dataclass(frozen=True, order=True)
class Edge:
    src: str
    dst: str
    edge_class: str
    provenance: str

    def __post_init__(self) -> None:
        if self.edge_class not in ALLOWED_EDGE_CLASSES:
            raise ValueError(f"unsupported edge class: {self.edge_class}")


@dataclass(frozen=True)
class GraphBuild:
    nodes: tuple[str, ...]
    edges: tuple[Edge, ...]
    changed_nodes: tuple[str, ...]
    unresolved_changed_paths: tuple[str, ...]
    parse_failed_changed_paths: tuple[str, ...]
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


def _unique_module_index(paths: Iterable[str]) -> dict[str, str]:
    candidates: dict[str, set[str]] = defaultdict(set)
    for path in paths:
        for alias in _module_aliases(path):
            candidates[alias].add(path)
    return {
        alias: next(iter(values))
        for alias, values in candidates.items()
        if len(values) == 1
    }


def _resolve_relative_module(current_path: str, level: int, module: str | None) -> str | None:
    parts = _module_parts(current_path)
    if not parts:
        return module
    package = list(parts[:-1])
    if level:
        remove = max(level - 1, 0)
        if remove > len(package):
            return None
        if remove:
            package = package[:-remove]
    if module:
        package.extend(module.split("."))
    return ".".join(package) if package else None


def _resolve_module(module: str | None, module_index: dict[str, str]) -> str | None:
    if not module:
        return None
    if module in module_index:
        return module_index[module]
    matches = {path for alias, path in module_index.items() if module.endswith(alias) or alias.endswith(module)}
    if len(matches) == 1:
        return next(iter(matches))
    return None


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


def _imported_modules(path: str, tree: ast.AST) -> tuple[str, ...]:
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            resolved = _resolve_relative_module(path, node.level, node.module)
            if resolved:
                modules.add(resolved)
            for alias in node.names:
                if alias.name == "*":
                    continue
                if resolved:
                    modules.add(f"{resolved}.{alias.name}")
    return tuple(sorted(modules))


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


def build_graph(
    *,
    sources: dict[str, str],
    changed_paths: list[str],
    behaviors: list[dict[str, Any]],
) -> GraphBuild:
    normalized_sources = {
        _normalize_path(path): text
        for path, text in sources.items()
        if _normalize_path(path).endswith(".py")
    }
    normalized_changed = tuple(sorted({_normalize_path(path) for path in changed_paths}))
    module_index = _unique_module_index(normalized_sources)

    source_symbols: dict[str, tuple[str, ...]] = {}
    source_imports: dict[str, tuple[str, ...]] = {}
    parse_failures: set[str] = set()
    for path, text in sorted(normalized_sources.items()):
        try:
            tree = ast.parse(text, filename=path)
        except (SyntaxError, ValueError):
            parse_failures.add(path)
            source_symbols[path] = ()
            source_imports[path] = ()
            continue
        source_symbols[path] = _top_level_symbols(tree)
        source_imports[path] = _imported_modules(path, tree)

    nodes: set[str] = {_file_node(path) for path in normalized_sources}
    nodes.update(_behavior_node(str(behavior["behavior_id"])) for behavior in behaviors)
    nodes.add("policy:critical")

    edges: list[Edge] = []
    for importer_path, modules in sorted(source_imports.items()):
        for module in modules:
            dependency_path = _resolve_module(module, module_index)
            if dependency_path is None or dependency_path == importer_path:
                continue
            # Impact flows from a changed dependency to its consumer.
            edges.append(
                Edge(
                    src=_file_node(dependency_path),
                    dst=_file_node(importer_path),
                    edge_class="static_program",
                    provenance=f"python_import:{module}",
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
        "parse_failed_changed_paths": list(parse_failed_changed),
    }
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return GraphBuild(
        nodes=tuple(sorted(nodes)),
        edges=unique_edges,
        changed_nodes=changed_nodes,
        unresolved_changed_paths=unresolved,
        parse_failed_changed_paths=parse_failed_changed,
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
    graph_digest: str,
    policy_selected: bool,
) -> dict[str, Any]:
    if policy_selected:
        return {
            "candidate_behavior_node": _behavior_node(behavior_id),
            "impact_path": ["policy:critical", _behavior_node(behavior_id)],
            "edge_classes": ["critical_invariant"],
            "edge_provenance": ["frozen_behavior_catalog:risk=critical"],
            "graph_digest": graph_digest,
            "policy_attribution": POLICY_ID,
        }
    assert path is not None
    return {
        "candidate_behavior_node": _behavior_node(behavior_id),
        "impact_path": [path[0].src, *(edge.dst for edge in path)] if path else [],
        "edge_classes": [edge.edge_class for edge in path],
        "edge_provenance": [edge.provenance for edge in path],
        "graph_digest": graph_digest,
        "policy_attribution": POLICY_ID,
    }


def _skip_proof(
    *,
    behavior_id: str,
    graph: GraphBuild,
    calibration_freshness: str,
    review: bool,
) -> dict[str, Any]:
    return {
        "changed_source_nodes": list(graph.changed_nodes),
        "candidate_behavior_node": _behavior_node(behavior_id),
        "edge_classes_considered": sorted(USED_EDGE_CLASSES),
        "no_path_reason": "no_admissible_path_from_changed_source_to_behavior",
        "uncertainty_state": "review_required" if review else "bounded_static_analysis",
        "calibration_freshness": calibration_freshness,
        "policy_attribution": POLICY_ID,
        "graph_digest": graph.graph_digest,
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

    review = bool(graph.unresolved_changed_paths or graph.parse_failed_changed_paths)
    reasons: list[str] = []
    if graph.unresolved_changed_paths:
        reasons.append(f"unresolved_changed_paths={len(graph.unresolved_changed_paths)}")
    if graph.parse_failed_changed_paths:
        reasons.append(f"parse_failed_changed_paths={len(graph.parse_failed_changed_paths)}")

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
                graph_digest=graph.graph_digest,
                policy_selected=True,
            )
        elif impact_path is not None:
            selected.add(behavior_id)
            selected_proofs[behavior_id] = _selected_proof(
                behavior_id=behavior_id,
                path=impact_path,
                graph_digest=graph.graph_digest,
                policy_selected=False,
            )

    if review:
        # Fail-safe widening mirrors the frozen benchmark safety policy: ambiguity
        # may increase evidence or force REVIEW, never justify a smaller suite.
        for behavior in behaviors:
            if not _risk_at_least(behavior, "high"):
                continue
            behavior_id = str(behavior["behavior_id"])
            if behavior_id in selected:
                continue
            selected.add(behavior_id)
            selected_proofs[behavior_id] = {
                "candidate_behavior_node": _behavior_node(behavior_id),
                "impact_path": [],
                "edge_classes": [],
                "edge_provenance": [],
                "graph_digest": graph.graph_digest,
                "policy_attribution": f"{POLICY_ID}:uncertainty_widen_high_critical",
            }
        reasons.append("uncertainty:widen_high_critical")

    skip_proofs = {
        str(behavior["behavior_id"]): _skip_proof(
            behavior_id=str(behavior["behavior_id"]),
            graph=graph,
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

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

JSON = dict[str, Any]


class Risk(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    @property
    def rank(self) -> int:
        return {Risk.LOW: 1, Risk.MEDIUM: 2, Risk.HIGH: 3, Risk.CRITICAL: 4}[self]


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return {
            Severity.INFO: 0,
            Severity.LOW: 1,
            Severity.MEDIUM: 2,
            Severity.HIGH: 3,
            Severity.CRITICAL: 4,
        }[self]


class ChangeType(str, Enum):
    AGENT_CONFIG_CHANGED = "AGENT_CONFIG_CHANGED"
    MODEL_CHANGED = "MODEL_CHANGED"
    PROVIDER_CHANGED = "PROVIDER_CHANGED"
    SYSTEM_INSTRUCTION_CHANGED = "SYSTEM_INSTRUCTION_CHANGED"
    TOOL_ADDED = "TOOL_ADDED"
    TOOL_REMOVED = "TOOL_REMOVED"
    TOOL_DESCRIPTION_CHANGED = "TOOL_DESCRIPTION_CHANGED"
    TOOL_SAFETY_METADATA_CHANGED = "TOOL_SAFETY_METADATA_CHANGED"
    TOOL_CONFIGURATION_CHANGED = "TOOL_CONFIGURATION_CHANGED"
    TOOL_INPUT_SCHEMA_EXPANDED = "TOOL_INPUT_SCHEMA_EXPANDED"
    TOOL_INPUT_SCHEMA_RESTRICTED = "TOOL_INPUT_SCHEMA_RESTRICTED"
    TOOL_SCHEMA_CHANGED = "TOOL_SCHEMA_CHANGED"
    MCP_SERVER_CHANGED = "MCP_SERVER_CHANGED"
    POLICY_CHANGED = "POLICY_CHANGED"
    POLICY_SCOPE_EXPANDED = "POLICY_SCOPE_EXPANDED"
    RETRIEVAL_CORPUS_CHANGED = "RETRIEVAL_CORPUS_CHANGED"
    RUNTIME_CONFIG_CHANGED = "RUNTIME_CONFIG_CHANGED"
    SOURCE_CODE_CHANGED = "SOURCE_CODE_CHANGED"
    UNCLASSIFIED_CHANGE = "UNCLASSIFIED_CHANGE"


class DecisionStatus(str, Enum):
    PASS = "PASS"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


class ResultStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    MISSING = "missing"


@dataclass(frozen=True)
class Change:
    type: ChangeType
    path: str
    severity: Severity
    summary: str
    tool: str | None = None
    capability: str | None = None
    before_digest: str | None = None
    after_digest: str | None = None
    metadata: JSON = field(default_factory=dict)

    def to_dict(self) -> JSON:
        data = asdict(self)
        data["type"] = self.type.value
        data["severity"] = self.severity.value
        return data


@dataclass(frozen=True)
class ChangeSet:
    baseline_digest: str
    candidate_digest: str
    changes: tuple[Change, ...]

    @property
    def is_empty(self) -> bool:
        return not self.changes

    @property
    def highest_severity(self) -> Severity:
        if not self.changes:
            return Severity.INFO
        return max((item.severity for item in self.changes), key=lambda item: item.rank)

    def to_dict(self) -> JSON:
        return {
            "baseline_digest": self.baseline_digest,
            "candidate_digest": self.candidate_digest,
            "highest_severity": self.highest_severity.value,
            "changes": [item.to_dict() for item in self.changes],
        }


@dataclass(frozen=True)
class ContractCoverage:
    tools: tuple[str, ...] = ()
    change_types: tuple[ChangeType, ...] = ()
    manifest_paths: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()

    def to_dict(self) -> JSON:
        return {
            "tools": list(self.tools),
            "change_types": [item.value for item in self.change_types],
            "manifest_paths": list(self.manifest_paths),
            "capabilities": list(self.capabilities),
        }


@dataclass(frozen=True)
class Expectations:
    required_sequence: tuple[str, ...] = ()
    forbidden_tools: tuple[str, ...] = ()
    required_tools: tuple[str, ...] = ()
    max_tool_calls: dict[str, int] = field(default_factory=dict)
    output_contains: tuple[str, ...] = ()
    output_not_contains: tuple[str, ...] = ()
    output_min_length: int = 0
    budgets: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> JSON:
        return {
            "required_sequence": list(self.required_sequence),
            "forbidden_tools": list(self.forbidden_tools),
            "required_tools": list(self.required_tools),
            "max_tool_calls": self.max_tool_calls,
            "output_contains": list(self.output_contains),
            "output_not_contains": list(self.output_not_contains),
            "output_min_length": self.output_min_length,
            "budgets": self.budgets,
        }


@dataclass(frozen=True)
class Contract:
    id: str
    title: str
    risk: Risk
    tags: tuple[str, ...]
    always_run: bool
    coverage: ContractCoverage
    expectations: Expectations
    source: str

    def to_dict(self) -> JSON:
        return {
            "id": self.id,
            "title": self.title,
            "risk": self.risk.value,
            "tags": list(self.tags),
            "always_run": self.always_run,
            "coverage": self.coverage.to_dict(),
            "expectations": self.expectations.to_dict(),
            "source": self.source,
        }


@dataclass(frozen=True)
class SelectionReason:
    contract_id: str
    reasons: tuple[str, ...]

    def to_dict(self) -> JSON:
        return {"contract_id": self.contract_id, "reasons": list(self.reasons)}


@dataclass(frozen=True)
class Selection:
    selected_ids: tuple[str, ...]
    reasons: tuple[SelectionReason, ...]
    uncovered_changes: tuple[int, ...]
    fallback_applied: bool
    total_contracts: int

    @property
    def reduction_ratio(self) -> float:
        if self.total_contracts == 0:
            return 0.0
        return 1.0 - (len(self.selected_ids) / self.total_contracts)

    def to_dict(self) -> JSON:
        return {
            "selected_ids": list(self.selected_ids),
            "reasons": [item.to_dict() for item in self.reasons],
            "uncovered_changes": list(self.uncovered_changes),
            "fallback_applied": self.fallback_applied,
            "total_contracts": self.total_contracts,
            "selected_contracts": len(self.selected_ids),
            "reduction_ratio": self.reduction_ratio,
        }


@dataclass(frozen=True)
class TraceEvent:
    type: str
    name: str | None = None
    content: str | None = None
    arguments: JSON = field(default_factory=dict)
    metadata: JSON = field(default_factory=dict)

    @property
    def token(self) -> str:
        if self.name:
            return f"{self.type}:{self.name}"
        return self.type

    def to_dict(self) -> JSON:
        return {
            "type": self.type,
            "name": self.name,
            "content": self.content,
            "arguments": self.arguments,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class TraceRecord:
    case_id: str
    events: tuple[TraceEvent, ...]
    output: str
    metrics: dict[str, float]
    metadata: JSON = field(default_factory=dict)

    def to_dict(self) -> JSON:
        return {
            "case_id": self.case_id,
            "events": [event.to_dict() for event in self.events],
            "output": self.output,
            "metrics": self.metrics,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class AssertionResult:
    assertion: str
    passed: bool
    detail: str

    def to_dict(self) -> JSON:
        return asdict(self)


@dataclass(frozen=True)
class ContractResult:
    contract_id: str
    risk: Risk
    status: ResultStatus
    assertions: tuple[AssertionResult, ...]
    metrics: dict[str, float]

    @property
    def passed(self) -> bool:
        return self.status is ResultStatus.PASS

    def to_dict(self) -> JSON:
        return {
            "contract_id": self.contract_id,
            "risk": self.risk.value,
            "status": self.status.value,
            "assertions": [item.to_dict() for item in self.assertions],
            "metrics": self.metrics,
        }


@dataclass(frozen=True)
class Comparison:
    contract_id: str
    baseline: ResultStatus
    candidate: ResultStatus
    classification: str
    risk: Risk

    def to_dict(self) -> JSON:
        return {
            "contract_id": self.contract_id,
            "baseline": self.baseline.value,
            "candidate": self.candidate.value,
            "classification": self.classification,
            "risk": self.risk.value,
        }


@dataclass(frozen=True)
class DecisionReason:
    code: str
    message: str
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> JSON:
        return {"code": self.code, "message": self.message, "evidence": list(self.evidence)}


@dataclass(frozen=True)
class Decision:
    status: DecisionStatus
    reasons: tuple[DecisionReason, ...]
    summary: JSON

    def to_dict(self) -> JSON:
        return {
            "status": self.status.value,
            "reasons": [item.to_dict() for item in self.reasons],
            "summary": self.summary,
        }

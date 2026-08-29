"""ProofDiff public package interface."""

from proofdiff._version import __version__ as __version__
from proofdiff.domain.models import Decision as Decision
from proofdiff.domain.models import DecisionStatus as DecisionStatus
from proofdiff.engine.pipeline import CheckRequest as CheckRequest
from proofdiff.engine.pipeline import run_check as run_check

__all__ = ["CheckRequest", "Decision", "DecisionStatus", "__version__", "run_check"]

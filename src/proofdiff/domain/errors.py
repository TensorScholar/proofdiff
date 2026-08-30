class ProofDiffError(Exception):
    """Base class for expected user-facing errors."""


class InputError(ProofDiffError):
    """Raised when an input artifact is invalid or unsafe to process."""


class VerificationError(ProofDiffError):
    """Raised when an evidence bundle fails integrity verification."""

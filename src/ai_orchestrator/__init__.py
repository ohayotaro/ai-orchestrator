"""Project-driven orchestration. Stable trusted-local control plane."""

__version__ = "1.0.1"

# Capture loaded source identity before a long-lived host can observe an editable update.
from .build_identity import _LOADED_DIGEST as __build_digest__

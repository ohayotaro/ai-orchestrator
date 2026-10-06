"""Project-driven orchestration. Trusted-local hardening release."""

__version__ = "0.17.0"

# Capture loaded source identity before a long-lived host can observe an editable update.
from .build_identity import _LOADED_DIGEST as __build_digest__

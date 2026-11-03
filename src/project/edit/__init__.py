"""Typed edit transactions and CAS helpers for the project ledger."""

from .cas import cas_set, read_entity_revision

__all__ = ["cas_set", "read_entity_revision"]

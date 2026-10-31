"""Admission, queue, dispatch, isolated workers, cancel, evidence, evaluation. Owns execution."""

from .block_runs_scope import (
    BLOCK_RUN_OPERATIONS,
    BLOCK_SCOPE,
    PROJECT_SCOPE,
    SUPPORTED_SCOPES,
    BlockScopeError,
    build_scope_record,
    check_operation_scope,
    closure_hash,
    narrow_job_for_block,
    parse_target,
    resolve_block,
    scope_provenance,
    snapshot_closure,
    stamp_verdict,
)
from .console import ConsoleSession, get_help
from .dispatch import OpDispatcher, parse_op_call, parse_op_tokens
from .errors import ExecutionError, UsageError
from .runner import BwrapRunner
from .service import ExecutionService
from .worker import CellRunner, CredentialGate, worker_profile

__all__ = [
    "BLOCK_RUN_OPERATIONS",
    "BLOCK_SCOPE",
    "PROJECT_SCOPE",
    "SUPPORTED_SCOPES",
    "BlockScopeError",
    "BwrapRunner",
    "CellRunner",
    "ConsoleSession",
    "CredentialGate",
    "ExecutionError",
    "ExecutionService",
    "OpDispatcher",
    "UsageError",
    "build_scope_record",
    "check_operation_scope",
    "closure_hash",
    "get_help",
    "narrow_job_for_block",
    "parse_op_call",
    "parse_op_tokens",
    "parse_target",
    "resolve_block",
    "scope_provenance",
    "snapshot_closure",
    "stamp_verdict",
    "worker_profile",
]

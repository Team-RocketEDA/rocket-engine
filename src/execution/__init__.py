"""Admission, queue, dispatch, isolated workers, cancel, evidence, evaluation. Owns execution."""

from .apig_pool import (
    ApigPool,
    pending_from_events,
    request_for_run,
    stored_completion_from_events,
)
from .apig_submit import SubmitImmediate, merge_ack_completion
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
    "ApigPool",
    "BlockScopeError",
    "BwrapRunner",
    "CellRunner",
    "ConsoleSession",
    "CredentialGate",
    "ExecutionError",
    "ExecutionService",
    "OpDispatcher",
    "SubmitImmediate",
    "UsageError",
    "build_scope_record",
    "check_operation_scope",
    "closure_hash",
    "get_help",
    "merge_ack_completion",
    "narrow_job_for_block",
    "parse_op_call",
    "parse_op_tokens",
    "parse_target",
    "pending_from_events",
    "request_for_run",
    "resolve_block",
    "scope_provenance",
    "snapshot_closure",
    "stamp_verdict",
    "stored_completion_from_events",
    "worker_profile",
]

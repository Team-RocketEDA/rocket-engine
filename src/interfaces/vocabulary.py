"""Operation vocabulary: the single source of truth for callable names.

Transports gate inbound names against these sets; the composition root
gates outbound routing against them. Neither side keeps its own copy.
"""

OPERATIONS = frozenset(
    {
        "generate_views", "run_hdl_test", "run_formal", "run_syntax",
        "run_connectivity", "run_drc", "run_lvs", "run_erc", "run_spice",
        "run_optical", "run_digital_flow", "run_timing", "run_extraction",
        "run_post_layout", "run_em", "run_thermal", "python_execute",
        "run_view_sync", "run_job",
    }
)
QUERIES = frozenset(
    {
        "api_search", "api_info", "api_help", "get_python_console",
        "get_capabilities", "get_project_snapshot", "list_job_kinds",
        "plan_checks", "get_job_status", "get_check_results",
        "get_events_since", "list_artifacts", "get_logs",
    }
)

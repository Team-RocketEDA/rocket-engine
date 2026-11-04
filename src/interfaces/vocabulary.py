"""Operation vocabulary: the single source of truth for callable names.

Transports gate inbound names against these sets; the composition root
gates outbound routing against them. Neither side keeps its own copy.
"""

OPERATIONS = frozenset(
    {
        "generate_views", "run_hdl_test", "run_formal", "run_syntax",
        "run_synth",
        "run_connectivity", "run_drc", "run_lvs", "run_erc", "run_spice",
        "run_optical", "run_digital_flow", "run_timing", "run_extraction",
        "run_post_layout", "run_em", "run_thermal", "python_execute",
        "run_view_sync", "run_cosim", "run_xschem", "run_antenna",
        "python_open", "python_reset",
        "run_job",
        "resume_run", "discard_run", "resume_all_retryable", "cancel_job",
        "create_project", "write_doc", "delete_doc", "apply_mutations",
        "rewind", "place_cell", "write_settings",
        "create_entity", "set_component", "attach_component",
        "detach_component", "delete_entity",
        "place_wire", "place_junction", "connect_endpoint", "move_wire",
        "split_wire", "delete_wire", "delete_junction", "materialize_nets",
        "apply_transaction",
        "create_shape",
        "create_sheet", "place_instance", "bind_block",
        "create_symbol", "create_cell", "map_pins",
        "ip_register", "ip_instantiate", "ip_promote",
        "bind_layers", "annotate",
        "create_testbench", "regenerate_testbench",
    }
)
QUERIES = frozenset(
    {
        "api_search", "api_info", "api_help", "get_python_console",
        "get_capabilities", "get_project_snapshot", "list_job_kinds",
        "plan_checks", "get_design_completion",
        "get_job_status", "get_check_results",
        "get_events_since", "list_artifacts", "get_logs",
        "get_findings",
        "list_projects", "list_docs", "read_doc",
        "get_component", "components_of", "entities_with",
        "get_world_snapshot",
        "list_cells", "serve_asset", "list_assets",
        "read_settings", "get_resolved_config",
        "get_layer_stackup", "get_layer_rows", "list_layer_presets",
        "save_layer_preset", "delete_layer_preset", "apply_layer_preset",
        "list_survivors",
        "read_entity_revision",
        "list_sheets", "get_sheet", "get_instance", "instances_on_sheet",
        "list_symbols", "get_symbol", "get_cell",
        "list_layers", "check_capability",
        "ip_search", "ip_get",
        "connection_graph", "net_occurrences", "xprobe", "resolve_pin",
        "plot_export", "erc_check", "write_netlist", "update_netlist",
        "list_testbenches", "describe_testbench",
    }
)

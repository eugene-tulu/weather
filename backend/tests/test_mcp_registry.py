from __future__ import annotations


def test_mcp_tools_registered():
    import mcp_server

    names = set(mcp_server.mcp._tool_manager._tools)
    assert {
        "list_sites",
        "get_site",
        "forecast_site",
        "workability_window",
        "risk_flags",
        "get_usage",
        "get_operations",
        "get_data_provenance",
    } <= names

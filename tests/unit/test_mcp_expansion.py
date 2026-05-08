import ast
from pathlib import Path

from dadosbr.mcp.server import (
    ASSET_MASTER_TOOL_NAMES,
    BENCHMARK_TOOL_NAMES,
    CORPORATE_ACTION_TOOL_NAMES,
    DERIVATIVES_TOOL_NAMES,
    EXPANSION_TOOL_NAMES,
    FIXED_INCOME_TOOL_NAMES,
    FUNDAMENTALS_TOOL_NAMES,
    INTEREST_CURVE_TOOL_NAMES,
    TIMESERIES_TOOL_NAMES,
    _validate_mcp_admin,
    _validate_mcp_local_path,
)


def _registered_mcp_tool_names() -> set[str]:
    module = ast.parse(Path("src/dadosbr/mcp/server.py").read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(module):
        if not isinstance(node, ast.FunctionDef):
            continue
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
                if decorator.func.attr == "tool":
                    names.add(node.name)
    return names


def test_mcp_tool_registry_matches_current_contract() -> None:
    tool_names = _registered_mcp_tool_names()

    assert len(tool_names) == 73
    assert {
        "parse_b3_cotahist_text",
        "parse_derivatives_futures_text",
        "get_tesouro_interest_curve",
    }.issubset(tool_names)


def test_mcp_tools_have_descriptions_for_clients() -> None:
    module = ast.parse(Path("src/dadosbr/mcp/server.py").read_text(encoding="utf-8"))
    missing_descriptions: list[str] = []
    for node in ast.walk(module):
        if not isinstance(node, ast.FunctionDef):
            continue
        is_tool = any(
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr == "tool"
            for decorator in node.decorator_list
        )
        if is_tool and not ast.get_docstring(node):
            missing_descriptions.append(node.name)

    assert missing_descriptions == []


def test_admin_sync_cnpj_tool_requires_mcp_admin_validation() -> None:
    module = ast.parse(Path("src/dadosbr/mcp/server.py").read_text(encoding="utf-8"))
    functions = [node for node in ast.walk(module) if isinstance(node, ast.FunctionDef)]
    admin_tool = next(node for node in functions if node.name == "admin_sync_cnpj")

    assert "admin_token" in {arg.arg for arg in admin_tool.args.args}
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_validate_mcp_admin"
        for node in ast.walk(admin_tool)
    )


def test_expansion_tool_names_present() -> None:
    expected = {
        "get_cnpj_status",
        "get_cnpj_company",
        "search_cnpj_companies",
        "get_cnpj_partners",
        "get_comex_ncm",
        "summarize_comex_ncm",
        "get_comex_municipality",
        "get_comex_table",
        "get_bndes_operations",
        "get_bndes_variable_income",
        "list_bndes_datasets",
    }
    assert expected == EXPANSION_TOOL_NAMES


def test_asset_master_tool_names_present() -> None:
    expected = {
        "get_asset_master",
        "search_asset_master",
        "get_issuer_master",
        "get_instrument_master",
        "get_cnae_taxonomy",
        "get_ncm_taxonomy",
    }
    assert expected == ASSET_MASTER_TOOL_NAMES


def test_timeseries_tool_names_present() -> None:
    expected = {
        "get_asset_price_history",
        "get_economic_timeseries",
        "read_timeseries_store",
        "write_asset_history_to_store",
    }
    assert expected == TIMESERIES_TOOL_NAMES


def test_benchmark_tool_names_present() -> None:
    expected = {
        "list_benchmarks",
        "get_benchmark_metadata",
        "get_benchmark_history",
        "get_real_benchmark_history",
        "compare_asset_to_benchmark",
        "get_yield_curve",
        "list_macro_calendar",
    }
    assert expected == BENCHMARK_TOOL_NAMES


def test_fixed_income_tool_names_present() -> None:
    expected = {
        "get_tesouro_fixed_income",
        "get_private_credit_debentures",
        "get_fund_fixed_income_exposure",
        "get_fixed_income_cashflows",
        "get_fixed_income_analytics",
        "get_fixed_income_credit_spread_curve",
    }
    assert expected == FIXED_INCOME_TOOL_NAMES


def test_fundamentals_tool_names_present() -> None:
    expected = {
        "get_company_fundamentals",
        "get_company_statement",
        "get_company_ratios",
        "get_company_dividends",
        "compare_companies_fundamentals",
        "list_fundamentals_calendar",
    }
    assert expected == FUNDAMENTALS_TOOL_NAMES


def test_corporate_action_tool_names_present() -> None:
    expected = {
        "list_corporate_action_types",
        "get_corporate_actions",
        "get_corporate_action_factors",
        "get_corporate_action_adjusted_history",
        "normalize_corporate_actions",
    }
    assert expected == CORPORATE_ACTION_TOOL_NAMES


def test_derivatives_tool_names_present() -> None:
    expected = {
        "list_derivative_families",
        "normalize_futures_quotes",
        "get_derivative_futures_from_file",
        "parse_derivatives_futures_text",
        "normalize_options_chain",
    }
    assert expected == DERIVATIVES_TOOL_NAMES


def test_interest_curve_tool_names_present() -> None:
    expected = {
        "list_interest_curve_sources",
        "get_tesouro_interest_curve",
        "normalize_interest_curve_points",
        "normalize_anbima_curve_rows",
        "build_di_curve_from_futures",
        "interpolate_interest_curve",
        "calculate_discount_factors",
        "calculate_forward_rates",
    }
    assert expected == INTEREST_CURVE_TOOL_NAMES


def test_mcp_local_path_validation_blocks_paths_by_default(monkeypatch, tmp_path) -> None:
    marker = tmp_path / "derivatives.csv"
    marker.write_text("symbol\nDI1F27\n", encoding="utf-8")

    monkeypatch.delenv("DADOSBR_ENABLE_LOCAL_FILE_ENDPOINTS", raising=False)

    path, error = _validate_mcp_local_path(str(marker), purpose="derivatives_file", source_id="derivatives")

    assert path == ""
    assert error is not None
    assert error["ok"] is False
    assert error["error"]["code"] == "local_file_access_disabled"


def test_mcp_local_path_validation_allows_configured_root(monkeypatch, tmp_path) -> None:
    marker = tmp_path / "derivatives.csv"
    marker.write_text("symbol\nDI1F27\n", encoding="utf-8")

    monkeypatch.setenv("DADOSBR_ENABLE_LOCAL_FILE_ENDPOINTS", "1")
    monkeypatch.setenv("DADOSBR_LOCAL_DATA_DIR", str(tmp_path))

    path, error = _validate_mcp_local_path(str(marker), purpose="derivatives_file", source_id="derivatives")

    assert error is None
    assert path == str(marker.resolve())


def test_mcp_admin_validation_blocks_sync_by_default(monkeypatch) -> None:
    monkeypatch.delenv("DADOSBR_ENABLE_ADMIN_MCP", raising=False)
    monkeypatch.setenv("DADOSBR_ADMIN_TOKEN", "secret-token")

    error = _validate_mcp_admin("", purpose="admin/cnpj/sync", source_id="receita_cnpj")

    assert error is not None
    assert error["ok"] is False
    assert error["error"]["code"] == "admin_mcp_disabled"


def test_mcp_admin_validation_requires_configured_token(monkeypatch) -> None:
    monkeypatch.setenv("DADOSBR_ENABLE_ADMIN_MCP", "1")
    monkeypatch.delenv("DADOSBR_ADMIN_TOKEN", raising=False)

    error = _validate_mcp_admin("", purpose="admin/cnpj/sync", source_id="receita_cnpj")

    assert error is not None
    assert error["ok"] is False
    assert error["error"]["code"] == "admin_token_required"


def test_mcp_admin_validation_allows_valid_token(monkeypatch) -> None:
    monkeypatch.setenv("DADOSBR_ENABLE_ADMIN_MCP", "1")
    monkeypatch.setenv("DADOSBR_ADMIN_TOKEN", "secret-token")

    error = _validate_mcp_admin("secret-token", purpose="admin/cnpj/sync", source_id="receita_cnpj")

    assert error is None

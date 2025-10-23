import pytest
from pydantic import ValidationError

from mcp_servers.ham3d_mysql import ProductSearchRequest, _build_where_clause


def test_price_range_validation() -> None:
    with pytest.raises(ValidationError):
        ProductSearchRequest(min_price=500, max_price=100)


def test_overlap_validation() -> None:
    with pytest.raises(ValidationError):
        ProductSearchRequest(product_ids=[1, 2], exclude_product_ids=[2])


def test_where_clause_contains_expected_filters() -> None:
    request = ProductSearchRequest(
        query="لباس",
        category_ids=[1, 16],
        color_names=["صورتی"],
        language="fa",
    )
    where, params = _build_where_clause(request)

    assert "p.lang = %s" in where
    assert "FIND_IN_SET(%s, p.catidby)" in where
    assert "c.title IN (%s)" in where
    assert params.count("fa") == 2  # language filter + colour subquery
    assert "c.state_show = 1" in where


def test_color_filter_disables_visibility_check() -> None:
    request = ProductSearchRequest(color_ids=[4], color_kind=0, only_visible_colors=False)
    where, params = _build_where_clause(request)

    assert "pct.colorid IN (%s)" in where
    assert "pct.kind = %s" in where
    assert "c.state_show = 1" not in where
    # colour filter should not duplicate parameters unnecessarily
    assert params == ["fa", 4, 0, "fa"]

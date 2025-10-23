"""MCP server exposing search over the ham3d MySQL catalogue."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable, Sequence

import aiomysql
from mcp.server.fastmcp import Context, FastMCP
from pydantic import BaseModel, Field, field_validator, model_validator

LOGGER = logging.getLogger(__name__)


class SortOption(str):
    """Sort identifiers supported by the search endpoint."""

    LATEST = "latest"
    OLDEST = "oldest"
    MOST_VIEWED = "most_viewed"
    BEST_SELLING = "best_selling"
    PRICE_LOW_HIGH = "price_low_high"
    PRICE_HIGH_LOW = "price_high_low"

    @classmethod
    def all(cls) -> tuple[str, ...]:
        return (
            cls.LATEST,
            cls.OLDEST,
            cls.MOST_VIEWED,
            cls.BEST_SELLING,
            cls.PRICE_LOW_HIGH,
            cls.PRICE_HIGH_LOW,
        )


class ProductColor(BaseModel):
    """Color variant metadata for a product."""

    id: int = Field(alias="color_id")
    title: str
    hex_code: str | None = Field(default=None, alias="color_hex")
    kind: int | None = None
    variant_title: str | None = Field(default=None, description="Custom label for the price/color row")
    asset_path: str | None = Field(default=None, description="Relative image path for this variant")


class ProductResult(BaseModel):
    """Product data returned to the MCP client."""

    id: int
    code: str | None = None
    title: str
    title_english: str | None = None
    language: str
    main_category_id: int | None = None
    category_id: int | None = None
    category_ids: list[int] = Field(default_factory=list)
    brand_id: int | None = None
    price: int | None = None
    price_text: str | None = None
    view_count: int | None = Field(default=None, alias="hit")
    sell_count: int | None = Field(default=None, alias="sell")
    discount_percent: int | None = None
    state: int | None = None
    active: bool | None = None
    image: str | None = Field(default=None, alias="pic")
    alt_image: str | None = Field(default=None, alias="alt_pic")
    tags: list[str] = Field(default_factory=list)
    colors: list[ProductColor] = Field(default_factory=list)

    @field_validator("tags", mode="before")
    @classmethod
    def _normalise_tags(cls, value: Any) -> list[str]:
        if not value:
            return []
        if isinstance(value, str):
            raw = [item.strip() for chunk in value.splitlines() for item in chunk.split(",")]
            return [item for item in raw if item]
        if isinstance(value, Iterable):
            return [str(item).strip() for item in value if str(item).strip()]
        return [str(value).strip()]

    @field_validator("category_ids", mode="before")
    @classmethod
    def _normalise_categories(cls, value: Any) -> list[int]:
        if not value:
            return []
        if isinstance(value, str):
            items = [chunk.strip() for chunk in value.split(",") if chunk.strip()]
            return [int(item) for item in items if item.isdigit()]
        return [int(item) for item in value if str(item).strip()]

    @field_validator("price", mode="before")
    @classmethod
    def _normalise_price(cls, value: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return int(value)
        if isinstance(value, (int, float)):
            return int(value)
        text = str(value).strip()
        if not text:
            return None
        try:
            return int(float(text))
        except ValueError:
            return None

    @field_validator("view_count", "sell_count", "discount_percent", "state", mode="before")
    @classmethod
    def _to_int(cls, value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @field_validator("active", mode="before")
    @classmethod
    def _to_bool(cls, value: Any) -> bool | None:
        if value in {None, "", "NULL"}:
            return None
        if isinstance(value, bool):
            return value
        try:
            return bool(int(value))
        except (TypeError, ValueError):
            return None


class ProductSearchRequest(BaseModel):
    """Structured input accepted by the ``search_products`` MCP tool."""

    query: str | None = Field(default=None, description="Full-text fragment to match against product titles and SEO metadata.")
    language: str | None = Field(default="fa", description="Restrict results to a specific language code.")
    category_ids: list[int] | None = Field(default=None, description="Match any of these category identifiers (catid/maincatid).")
    brand_ids: list[int] | None = Field(default=None, description="Restrict results to one of the listed brand identifiers.")
    product_ids: list[int] | None = Field(default=None, description="Fetch products with these exact identifiers.")
    exclude_product_ids: list[int] | None = Field(default=None, description="Skip products with these identifiers.")
    color_ids: list[int] | None = Field(default=None, description="Require at least one colour variant with these identifiers.")
    color_names: list[str] | None = Field(default=None, description="Require colour variants that match one of these names.")
    color_kind: int | None = Field(default=None, description="Filter colour variants by their ``kind`` flag.")
    only_active: bool = Field(default=True, description="Return only products where the `active` flag is set.")
    only_visible_colors: bool = Field(default=True, description="Ignore colour variants that are hidden (state_show = 0).")
    min_price: int | None = Field(default=None, ge=0)
    max_price: int | None = Field(default=None, ge=0)
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    sort_by: str = Field(default=SortOption.LATEST, description="Sorting strategy.")

    @field_validator(
        "query",
        mode="before",
    )
    @classmethod
    def _normalise_query(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator(
        "category_ids",
        "brand_ids",
        "product_ids",
        "exclude_product_ids",
        "color_ids",
        mode="before",
    )
    @classmethod
    def _normalise_int_lists(cls, value: Any) -> list[int] | None:
        if value is None:
            return None
        if isinstance(value, (str, bytes)):
            text = value.decode() if isinstance(value, bytes) else value
            tokens = [token.strip() for token in text.split(",") if token.strip()]
        else:
            tokens = [value] if isinstance(value, (int, float)) else list(value)
        seen: list[int] = []
        for token in tokens:
            try:
                item = int(str(token).strip())
            except (TypeError, ValueError):
                continue
            if item not in seen:
                seen.append(item)
        return seen or None

    @field_validator("color_names", mode="before")
    @classmethod
    def _normalise_color_names(cls, value: Any) -> list[str] | None:
        if value is None:
            return None
        if isinstance(value, (str, bytes)):
            text = value.decode() if isinstance(value, bytes) else value
            tokens = [token.strip() for token in text.split(",") if token.strip()]
        else:
            tokens = [str(item).strip() for item in value if str(item).strip()]
        deduped: list[str] = []
        for token in tokens:
            lowered = token.lower()
            if lowered not in (entry.lower() for entry in deduped):
                deduped.append(token)
        return deduped or None

    @field_validator("sort_by")
    @classmethod
    def _validate_sort(cls, value: str) -> str:
        if value not in SortOption.all():
            raise ValueError(f"sort_by must be one of {', '.join(SortOption.all())}")
        return value

    @model_validator(mode="after")
    def _validate_price_range(self) -> "ProductSearchRequest":
        if self.min_price is not None and self.max_price is not None:
            if self.min_price > self.max_price:
                raise ValueError("min_price cannot be greater than max_price")
        if self.product_ids and self.exclude_product_ids:
            overlap = set(self.product_ids).intersection(self.exclude_product_ids)
            if overlap:
                raise ValueError("product_ids and exclude_product_ids cannot overlap")
        return self


class ProductSearchResponse(BaseModel):
    """Structured payload emitted by ``search_products``."""

    total: int
    count: int
    limit: int
    offset: int
    sort_by: str
    results: list[ProductResult]


@dataclass(slots=True)
class Ham3DLifespanContext:
    """Holds shared objects for the server lifespan."""

    pool: aiomysql.Pool


def _int_list_from_csv(csv_value: str | None) -> list[int]:
    if not csv_value:
        return []
    items: list[int] = []
    for chunk in csv_value.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            items.append(int(chunk))
        except ValueError:
            continue
    return items


def _build_where_clause(payload: ProductSearchRequest) -> tuple[str, list[Any]]:
    filters: list[str] = []
    params: list[Any] = []

    if payload.language:
        filters.append("p.lang = %s")
        params.append(payload.language)

    if payload.only_active:
        filters.append("p.active = 1")

    if payload.query:
        like = f"%{payload.query}%"
        filters.append(
            "(" "p.title LIKE %s OR p.title2 LIKE %s OR p.title_english LIKE %s OR "
            "p.seo_keywords LIKE %s OR p.seo_description LIKE %s OR p.tags LIKE %s" ")"
        )
        params.extend([like] * 6)

    if payload.category_ids:
        placeholders = ", ".join(["%s"] * len(payload.category_ids))
        category_clauses: list[str] = []
        category_clauses.append(f"p.catid IN ({placeholders})")
        params.extend(payload.category_ids)
        category_clauses.append(f"p.maincatid IN ({placeholders})")
        params.extend(payload.category_ids)
        for category_id in payload.category_ids:
            token = str(category_id)
            category_clauses.append("FIND_IN_SET(%s, p.catidby)")
            params.append(token)
            category_clauses.append("FIND_IN_SET(%s, p.catidby_full)")
            params.append(token)
        filters.append("(" + " OR ".join(category_clauses) + ")")

    if payload.brand_ids:
        placeholders = ", ".join(["%s"] * len(payload.brand_ids))
        filters.append(f"p.brandid IN ({placeholders})")
        params.extend(payload.brand_ids)

    if payload.product_ids:
        placeholders = ", ".join(["%s"] * len(payload.product_ids))
        filters.append(f"p.id IN ({placeholders})")
        params.extend(payload.product_ids)

    if payload.exclude_product_ids:
        placeholders = ", ".join(["%s"] * len(payload.exclude_product_ids))
        filters.append(f"p.id NOT IN ({placeholders})")
        params.extend(payload.exclude_product_ids)

    if payload.min_price is not None:
        filters.append("CAST(NULLIF(p.price, '') AS SIGNED) >= %s")
        params.append(payload.min_price)

    if payload.max_price is not None:
        filters.append("CAST(NULLIF(p.price, '') AS SIGNED) <= %s")
        params.append(payload.max_price)

    color_conditions: list[str] = []
    color_params: list[Any] = []
    if payload.color_ids:
        placeholders = ", ".join(["%s"] * len(payload.color_ids))
        color_conditions.append(f"pct.colorid IN ({placeholders})")
        color_params.extend(payload.color_ids)
    if payload.color_names:
        placeholders = ", ".join(["%s"] * len(payload.color_names))
        color_conditions.append(f"c.title IN ({placeholders})")
        color_params.extend(payload.color_names)
    if payload.color_kind is not None:
        color_conditions.append("pct.kind = %s")
        color_params.append(payload.color_kind)
    if payload.language:
        color_conditions.append("pct.lang = %s")
        color_params.append(payload.language)
    if payload.only_visible_colors:
        color_conditions.append("c.state_show = 1")

    if color_conditions:
        where = " AND ".join(color_conditions)
        filters.append(
            "EXISTS ("
            "SELECT 1 FROM ham3d_price_color_tab AS pct "
            "JOIN ham3d_product_color AS c ON c.id = pct.colorid "
            "WHERE pct.productid = p.id AND " + where + ")"
        )
        params.extend(color_params)

    where_clause = " AND ".join(filters) if filters else "1=1"
    return where_clause, params


SORT_SQL: dict[str, str] = {
    SortOption.LATEST: "p.date DESC",
    SortOption.OLDEST: "p.date ASC",
    SortOption.MOST_VIEWED: "p.hit DESC",
    SortOption.BEST_SELLING: "p.sell DESC",
    SortOption.PRICE_LOW_HIGH: "CAST(NULLIF(p.price, '') AS SIGNED) ASC",
    SortOption.PRICE_HIGH_LOW: "CAST(NULLIF(p.price, '') AS SIGNED) DESC",
}


async def _run_query(pool: aiomysql.Pool, query: str, params: Sequence[Any]) -> list[dict[str, Any]]:
    async with pool.acquire() as connection:
        async with connection.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(query, params)
            rows = await cursor.fetchall()
            return list(rows)


async def _fetch_catalog(
    pool: aiomysql.Pool,
    request: ProductSearchRequest,
) -> tuple[int, list[dict[str, Any]]]:
    where_clause, params = _build_where_clause(request)
    count_query = f"SELECT COUNT(DISTINCT p.id) AS total FROM ham3d_product AS p WHERE {where_clause}"

    sort_sql = SORT_SQL[request.sort_by]
    data_query = (
        "SELECT DISTINCT "
        "p.id, p.code, p.title, p.title_english, p.lang, p.maincatid, p.catid, p.catidby, p.catidby_full, "
        "p.brandid, p.price, p.price_text, p.hit, p.sell, p.discount_percent, p.state, p.active, "
        "p.pic, p.alt_pic, p.tags "
        "FROM ham3d_product AS p "
        f"WHERE {where_clause} "
        f"ORDER BY {sort_sql}, p.id DESC "
        "LIMIT %s OFFSET %s"
    )

    async with pool.acquire() as connection:
        async with connection.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(count_query, params)
            total_row = await cursor.fetchone()
            total = int(total_row.get("total", 0)) if total_row else 0

            data_params = list(params) + [request.limit, request.offset]
            await cursor.execute(data_query, data_params)
            rows = await cursor.fetchall()

    return total, list(rows)


async def _load_colors(
    pool: aiomysql.Pool,
    product_ids: Sequence[int],
    language: str | None,
    only_visible: bool,
) -> dict[int, list[ProductColor]]:
    if not product_ids:
        return {}

    placeholders = ", ".join(["%s"] * len(product_ids))
    query = (
        "SELECT pct.productid, pct.colorid, pct.kind, pct.title AS variant_title, pct.pic AS asset_path, "
        "c.title, c.color AS color_hex, c.state_show "
        "FROM ham3d_price_color_tab AS pct "
        "JOIN ham3d_product_color AS c ON c.id = pct.colorid "
        f"WHERE pct.productid IN ({placeholders})"
    )
    params: list[Any] = list(product_ids)

    if language:
        query += " AND pct.lang = %s"
        params.append(language)

    if only_visible:
        query += " AND c.state_show = 1"

    query += " ORDER BY pct.`order` ASC, pct.id ASC"

    rows = await _run_query(pool, query, params)
    grouped: dict[int, list[ProductColor]] = {}
    for row in rows:
        product_id = int(row.pop("productid"))
        grouped.setdefault(product_id, []).append(ProductColor(**row))
    return grouped


def _db_env(name: str, default: str | None = None, *, required: bool = False) -> str:
    value = os.getenv(name, default if default is not None else "")
    if required and not value:
        raise RuntimeError(f"Environment variable {name} must be configured for the ham3d server.")
    return value


@asynccontextmanager
async def lifespan(_: FastMCP) -> Iterable[Ham3DLifespanContext]:
    """Initialise and dispose the MySQL connection pool."""

    host = _db_env("HAM3D_DB_HOST", "127.0.0.1")
    port = int(_db_env("HAM3D_DB_PORT", "3306"))
    user = _db_env("HAM3D_DB_USER", required=True)
    password = _db_env("HAM3D_DB_PASSWORD", "")
    database = _db_env("HAM3D_DB_NAME", "ham3d")
    minsize = max(1, int(_db_env("HAM3D_DB_POOL_MIN_SIZE", "1")))
    maxsize = max(minsize, int(_db_env("HAM3D_DB_POOL_MAX_SIZE", "10")))
    connect_timeout = float(_db_env("HAM3D_DB_CONNECT_TIMEOUT", "10"))

    LOGGER.info(
        "Connecting to ham3d database on %s:%s with user %s (pool %s-%s)",
        host,
        port,
        user,
        minsize,
        maxsize,
    )

    pool = await aiomysql.create_pool(
        host=host,
        port=port,
        user=user,
        password=password,
        db=database,
        minsize=minsize,
        maxsize=maxsize,
        autocommit=True,
        charset="utf8mb4",
        connect_timeout=connect_timeout,
    )

    context = Ham3DLifespanContext(pool=pool)
    try:
        yield context
    finally:
        pool.close()
        await pool.wait_closed()


server = FastMCP(
    name="ham3d-mysql",
    instructions=(
        "Search ham3d catalogue items stored in MySQL. "
        "Use the `search_products` tool to filter by name, category, brand, price and colour variants."
    ),
    lifespan=lifespan,
)


@server.tool(
    name="search_products",
    title="Search ham3d products",
    description="Search the ham3d_product table using structured filters.",
    structured_output=True,
)
async def search_products(
    payload: ProductSearchRequest,
    ctx: Context[Any, Ham3DLifespanContext, Any],
) -> ProductSearchResponse:
    """Return products that satisfy the provided filters."""

    lifespan_context = ctx.request_context.lifespan_context
    pool = lifespan_context.pool

    total, rows = await _fetch_catalog(pool, payload)
    product_ids = [int(row["id"]) for row in rows]
    colors = await _load_colors(pool, product_ids, payload.language, payload.only_visible_colors)

    results: list[ProductResult] = []
    for row in rows:
        product_id = int(row["id"])
        category_ids = _int_list_from_csv(row.get("catidby"))
        category_ids_full = _int_list_from_csv(row.get("catidby_full"))
        merged_categories = sorted({*category_ids, *category_ids_full})

        result = ProductResult(
            id=product_id,
            code=row.get("code"),
            title=row.get("title", ""),
            title_english=row.get("title_english"),
            language=row.get("lang", ""),
            main_category_id=row.get("maincatid"),
            category_id=row.get("catid"),
            category_ids=merged_categories,
            brand_id=row.get("brandid"),
            price=row.get("price"),
            price_text=row.get("price_text"),
            view_count=row.get("hit"),
            sell_count=row.get("sell"),
            discount_percent=row.get("discount_percent"),
            state=row.get("state"),
            active=row.get("active"),
            image=row.get("pic"),
            alt_image=row.get("alt_pic"),
            tags=row.get("tags"),
            colors=colors.get(product_id, []),
        )
        results.append(result)

    return ProductSearchResponse(
        total=total,
        count=len(results),
        limit=payload.limit,
        offset=payload.offset,
        sort_by=payload.sort_by,
        results=results,
    )


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    server.run()

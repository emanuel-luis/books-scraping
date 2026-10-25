"""Pydantic contracts passed between the layers."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC)


UtcDatetime = Annotated[datetime, AfterValidator(_aware_utc)]


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ManifestEntry(_Model):
    url: str
    kind: Literal["robots", "listing", "product"]
    status: int  # 0 when no response arrived
    path: str | None  # relative to the run dir; None when no body was saved
    sha256: str | None = Field(pattern=r"^[0-9a-f]{64}$")
    bytes: int = Field(ge=0)
    fetched_at: UtcDatetime


class Book(_Model):
    upc: str = Field(pattern=r"^[0-9a-f]{16}$")
    url: str
    title: str = Field(min_length=1)
    category: str = Field(min_length=1)
    price: Decimal = Field(ge=0, decimal_places=2)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    stock: int = Field(ge=0)
    rating: int = Field(ge=1, le=5)
    num_reviews: int = Field(ge=0)
    description: str | None
    fetched_at: UtcDatetime
    run_id: str


class Reject(_Model):
    url: str
    path: str | None
    stage: Literal["integrity", "parse", "validate"]
    error: str


class StepSummary(_Model):
    run_id: str
    step: str
    status: Literal["ok", "failed"]
    started_at: UtcDatetime
    finished_at: UtcDatetime
    rows_in: int = 0
    rows_out: int = 0
    rows_rejected: int = 0
    listing_pages: int = 0
    product_pages: int = 0
    failed: int = 0
    skipped_robots: int = 0
    duplicates: int = 0


class FxRate(_Model):
    rate_date: date
    base: str
    quote: str
    rate: Decimal = Field(gt=0)
    source: str = "frankfurter (ECB)"
    fetched_at: UtcDatetime

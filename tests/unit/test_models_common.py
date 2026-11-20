import pytest
from pydantic import ValidationError

from entrepataseturnos_mcp.tools.models import LocalDate, OffsetDateTime, PageInput, PositiveId, StrictInput


class M(StrictInput):
    at: OffsetDateTime | None = None
    day: LocalDate | None = None
    pid: PositiveId | None = None


def test_offset_datetime() -> None:
    assert M(at="2026-12-01T14:00:00-03:00").at.utcoffset().total_seconds() == -3 * 3600  # type: ignore[union-attr,arg-type]
    assert M(at="2026-12-01T17:00:00Z").at is not None  # type: ignore[arg-type]
    for bad in ("2026-12-01T14:00:00", "2026-12-01", 1764608400, "tomorrow"):
        with pytest.raises(ValidationError):
            M(at=bad)  # type: ignore[arg-type]


def test_local_date() -> None:
    assert str(M(day="2026-12-01").day) == "2026-12-01"  # type: ignore[arg-type]
    for bad in ("01/12/2026", "2026-13-01", "2026-12-01T00:00:00-03:00"):
        with pytest.raises(ValidationError):
            M(day=bad)  # type: ignore[arg-type]


def test_positive_id() -> None:
    with pytest.raises(ValidationError):
        M(pid=0)
    with pytest.raises(ValidationError):
        M(pid="5")  # type: ignore[arg-type]


def test_page_bounds() -> None:
    assert PageInput().size == 20
    for kwargs in ({"size": 0}, {"size": 101}, {"page": -1}):
        with pytest.raises(ValidationError):
            PageInput(**kwargs)


@pytest.mark.parametrize("field", ["user_id", "owner_id", "account_id", "role"])
def test_identity_fields_rejected(field: str) -> None:
    with pytest.raises(ValidationError):
        M.model_validate({field: 1})

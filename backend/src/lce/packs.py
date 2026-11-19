"""Contract type packs.

A pack is configuration, not code: the summary fields, risk checklist and
sample contract for one kind of contract. Packs are validated when the app is
built, so a broken pack fails startup instead of failing mid-analysis.
"""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, create_model, field_validator

DATA = files("lce").joinpath("data")
BUNDLED_PACKS = ("general", "kenya_employment")  # the first is the default


class InvalidPack(ValueError):
    """A pack definition is missing data or inconsistent."""


class SummaryField(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: str
    description: str
    kind: Literal["single", "list"]


class RiskCategory(BaseModel):
    id: str
    label: str
    description: str


class Pack(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    name: str
    description: str
    sample_label: str = "Sample contract"
    summary_fields: list[SummaryField] = Field(min_length=1)
    risk_categories: list[RiskCategory] = Field(min_length=1)
    sample: str

    @field_validator("summary_fields")
    @classmethod
    def unique_field_names(cls, fields: list[SummaryField]) -> list[SummaryField]:
        names = [f.name for f in fields]
        if len(names) != len(set(names)):
            raise ValueError("summary field names must be unique")
        return fields

    @field_validator("risk_categories")
    @classmethod
    def unique_category_ids(cls, cats: list[RiskCategory]) -> list[RiskCategory]:
        ids = [c.id for c in cats]
        if len(ids) != len(set(ids)):
            raise ValueError("risk category ids must be unique")
        return cats

    @field_validator("sample")
    @classmethod
    def sample_exists(cls, name: str) -> str:
        if not DATA.joinpath(name).is_file():
            raise ValueError(f"sample {name!r} not found in lce/data")
        return name

    def sample_bytes(self) -> bytes:
        return DATA.joinpath(self.sample).read_bytes()

    def summary_model(self) -> type[BaseModel]:
        """Pydantic model for this pack's summary, used for the prompt schema and validation."""
        fields = {
            f.name: (str if f.kind == "single" else list[str], Field(description=f.description))
            for f in self.summary_fields
        }
        return create_model(f"{self.id.title().replace('_', '')}Summary", **fields)


def _read_bundled(pack_id: str) -> dict:
    return json.loads(DATA.joinpath("packs", f"{pack_id}.json").read_text())


def load_packs(raw: list[dict] | None = None) -> list[Pack]:
    """Validate pack definitions; ``None`` loads the bundled packs."""
    raw = raw if raw is not None else [_read_bundled(p) for p in BUNDLED_PACKS]
    packs: list[Pack] = []
    for item in raw:
        try:
            packs.append(Pack.model_validate(item))
        except ValidationError as e:
            label = item.get("id", "<no id>") if isinstance(item, dict) else "<not an object>"
            raise InvalidPack(f"Pack {label!r} is invalid:\n{e}") from None
    ids = [p.id for p in packs]
    if not packs:
        raise InvalidPack("At least one pack is required.")
    if len(ids) != len(set(ids)):
        raise InvalidPack(f"Duplicate pack ids: {ids}")
    return packs

# Generated boundary support; do not edit. Source: scripts/schema_models.py.
from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
from typing import Any, ClassVar

from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, RootModel, model_validator


def _plain(value):
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True, exclude_unset=True)
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


@lru_cache(maxsize=1)
def _schema():
    return json.loads(Path(__file__).with_name("schema.json").read_text())


@lru_cache(maxsize=None)
def _validator(pointer):
    schema = _schema()
    return Draft202012Validator({"$schema": schema["$schema"], "$defs": schema["$defs"], "$ref": pointer})


def _validate(pointer, value):
    plain = _plain(value)
    # Wire JSON has no NaN or Infinity, regardless of Python's JSON defaults.
    json.dumps(plain, allow_nan=False)
    errors = list(_validator(pointer).iter_errors(plain))
    if errors:
        first = errors[0]
        path = ".".join(str(item) for item in first.absolute_path)
        raise ValueError(f"{pointer} {path}: {first.message}")
    return plain


class ContractModel(BaseModel):
    """Typed boundary fields checked against the canonical wire schema."""
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)
    __schema_pointer__: ClassVar[str]

    @model_validator(mode="before")
    @classmethod
    def check_contract(cls, value):
        return _validate(cls.__schema_pointer__, value)

    def to_wire(self):
        """Serialize aliases and omit absent optional properties."""
        return self.model_dump(mode="json", by_alias=True, exclude_unset=True)


class ContractRoot(RootModel[Any]):
    """Canonical union preserving the unwrapped JSON shape."""
    model_config = ConfigDict(strict=True)
    __schema_pointer__: ClassVar[str]

    @model_validator(mode="before")
    @classmethod
    def check_contract(cls, value):
        return _validate(cls.__schema_pointer__, value)

    def to_wire(self):
        return self.model_dump(mode="json", by_alias=True, exclude_unset=True)

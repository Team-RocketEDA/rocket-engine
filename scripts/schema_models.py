"""Derive Python boundary DTOs from the canonical JSON Schema definitions.

Generated Pydantic models carry typed fields and validate serialized inputs
against the same schema used by TypeScript/transports. They are boundary types;
application/domain code can map them to framework-independent value objects.
"""
from __future__ import annotations

import json
import keyword
import re


class ModelEmitter:
    """Build deterministic typed Pydantic modules without a second shape source.

    Args:
        contract: Compiled canonical bundle with local schema references.
    """

    def __init__(self, contract):
        self.contract = contract
        self.definitions = contract['$defs']
        self.classes = {}
        self.aliases = {}
        self.used = set(self.definitions)

    def name(self, suggested):
        """Return an unused valid class name for an inline schema."""
        base = re.sub(r'[^A-Za-z0-9_]', '_', suggested)
        result, index = base, 2
        while result in self.used:
            result, index = base + str(index), index + 1
        self.used.add(result)
        return result

    def expression(self, schema, name, pointer):
        """Translate a field schema to an annotation and emit nested models."""
        if schema is True:
            return 'Any'
        if schema is False:
            return 'Never'
        if '$ref' in schema:
            return schema['$ref'].rsplit('/', 1)[1]
        if 'const' in schema:
            return 'Literal[' + repr(schema['const']) + ']'
        if 'enum' in schema:
            return 'Literal[' + ', '.join(repr(v) for v in schema['enum']) + ']'
        kind = schema.get('type')
        if isinstance(kind, list):
            return 'Union[' + ', '.join(self.expression({**schema, 'type': t}, name + str(i), pointer) for i, t in enumerate(kind)) + ']'
        variants = schema.get('oneOf', schema.get('anyOf'))
        if variants:
            models = []
            for i, variant in enumerate(variants):
                merged = variant
                if 'properties' in schema:
                    # Discriminated task alternatives refine base fields. A
                    # conditional target restriction is checked by JSON Schema;
                    # retain the complete Target DTO for structural typing.
                    props = dict(schema['properties'])
                    for key, value in variant.get('properties', {}).items():
                        if '$ref' in props.get(key, {}) and 'properties' in value:
                            continue
                        props[key] = value
                    merged = {**schema, **variant, 'properties': props,
                              'required': sorted(set(schema.get('required', [])) | set(variant.get('required', [])))}
                    merged.pop('oneOf', None)
                    merged.pop('anyOf', None)
                models.append(self.expression(merged, name + 'Variant' + str(i), pointer))
            return 'Union[' + ', '.join(models) + ']'
        if kind == 'object' or 'properties' in schema:
            if not schema.get('properties') and isinstance(schema.get('additionalProperties'), dict):
                value = self.expression(schema['additionalProperties'], name + 'Value', pointer)
                return f'dict[str, {value}]'
            nested = self.name(name)
            self.emit_class(nested, schema, pointer)
            return nested
        if kind == 'array':
            value = self.expression(schema.get('items', {}), name + 'Item', pointer + '/items')
            return f'list[{value}]'
        return {'string': 'str', 'number': 'float', 'integer': 'int',
                'boolean': 'bool', 'null': 'None'}.get(kind, 'Any')

    def emit_class(self, name, schema, pointer):
        """Emit a boundary class whose validator retains canonical semantics."""
        props = schema.get('properties', {})
        required = schema.get('required', [])
        lines = [f'class {name}(ContractModel):',
                 '    """Schema-derived boundary value; see canonical descriptions."""',
                 f'    __schema_pointer__: ClassVar[str] = {pointer!r}']
        for field, value in props.items():
            annotation = self.expression(value, name + '_' + field, pointer + '/properties/' + field)
            safe = field
            if keyword.iskeyword(safe) or safe in {'schema', 'json', 'copy', 'dict', 'validate', 'construct'} or safe.startswith('model_'):
                safe += '_'
            if not safe.isidentifier():
                safe = re.sub(r'\W', '_', safe)
            default = '' if field in required else 'None'
            if field not in required:
                annotation = f'Optional[{annotation}]'
            args = []
            if default:
                args.append('default=None')
            if safe != field:
                args.append('alias=' + repr(field))
            if value.get('description'):
                args.append('description=' + repr(value['description']))
            if args:
                suffix = ' = Field(' + ', '.join(args) + ')'
            else:
                suffix = ''
            lines.append(f'    {safe}: {annotation}{suffix}')
        self.classes[name] = '\n'.join(lines) + '\n'

    def emit(self):
        """Return generated files for the ordinary contract freshness check."""
        for name, schema in self.definitions.items():
            if name == 'JsonValue':
                self.aliases[name] = 'PydanticJsonValue'
            elif schema.get('type') == 'object' or ('properties' in schema and 'oneOf' not in schema):
                self.emit_class(name, schema, '#/$defs/' + name)
            elif 'oneOf' in schema or 'anyOf' in schema:
                annotation = self.expression(schema, name + 'Choice', '#/$defs/' + name)
                self.classes[name] = (f'class {name}(ContractRoot):\n'
                    '    """Canonical discriminated/union boundary value."""\n'
                    f'    __schema_pointer__: ClassVar[str] = {"#/$defs/" + name!r}\n'
                    f'    root: {annotation}\n')
            else:
                self.aliases[name] = self.expression(schema, name, '#/$defs/' + name)
        header = ('# Generated by scripts/check_v1_contract.py --write; do not edit.\n'
                  'from __future__ import annotations\n'
                  'from typing import Any, ClassVar, Literal, Never, Optional, Union\n'
                  'from pydantic import Field\n'
                  'from ..base import ContractModel, ContractRoot\n'
                  'from ..aliases import *\n\n')
        outputs = {'python/base.py': BASE,
                   'python/schema.json': json.dumps(self.contract, indent=2) + '\n',
                   'python/aliases.py': ('# Generated; do not edit.\nfrom typing import Any, Literal, Never, Optional, Union\n'
                       'from pydantic import JsonValue as PydanticJsonValue\n\n' +
                       '\n'.join(f'{name} = {value}' for name, value in self.aliases.items()) + '\n'),
                   'python/models/__init__.py': '# Generated model partitions.\n'}
        parts = []
        values = list(self.classes.values())
        for start in range(0, len(values), 70):
            part = 'part' + str(start // 70)
            outputs['python/models/' + part + '.py'] = header + '\n'.join(values[start:start + 70])
            parts.append(part)
        init = ['# Generated typed Pydantic boundary package; no provider implementation.',
                'from .aliases import *']
        init += ['from .models.' + part + ' import *' for part in parts]
        init += ['from .base import ContractModel, ContractRoot',
                 '_namespace = dict(globals())',
                 'for _name, _value in tuple(_namespace.items()):',
                 '    if isinstance(_value, type) and issubclass(_value, (ContractModel, ContractRoot)) and _value not in (ContractModel, ContractRoot):',
                 '        _value.model_rebuild(_types_namespace=_namespace)',
                 'del _namespace, _name, _value']
        outputs['python/__init__.py'] = '\n'.join(init) + '\n'
        return outputs


def render_python(contract):
    """Derive Python consumer DTOs from the compiled canonical bundle."""
    return ModelEmitter(contract).emit()


BASE = '''# Generated boundary support; do not edit. Source: scripts/schema_models.py.
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
'''

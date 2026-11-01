# Generated; do not edit.
from typing import Any, Literal, Never, Optional, Union
from pydantic import JsonValue as PydanticJsonValue

SampleQuality = Literal['valid', 'missing', 'invalid', 'not_converged']
OpaqueId = str
Revision = str
Hash = str
Scalar = Union[str, float, bool, None]
JsonValue = PydanticJsonValue
SpiceAnalysis = Literal['op', 'dc', 'ac', 'tran', 'noise', 'tf', 'pz', 'sens', 'disto', 'harmonic_balance']

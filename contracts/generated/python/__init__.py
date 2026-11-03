# Generated typed Pydantic boundary package; no provider implementation.
from .aliases import *
from .models.part0 import *
from .models.part1 import *
from .models.part2 import *
from .models.part3 import *
from .models.part4 import *
from .base import ContractModel, ContractRoot
_namespace = dict(globals())
for _name, _value in tuple(_namespace.items()):
    if isinstance(_value, type) and issubclass(_value, (ContractModel, ContractRoot)) and _value not in (ContractModel, ContractRoot):
        _value.model_rebuild(_types_namespace=_namespace)
del _namespace, _name, _value

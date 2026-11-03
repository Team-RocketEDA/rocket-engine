"""PDK-IHP RED — SAX RF models: rsil + inductor S-params at 5 GHz.

Valid RED = profile missing (FileNotFoundError) or sax/jax/ihp
unimportable (loud skip). GREEN evaluates the wrapper's own SAX
registry (ihp.models.sax, 10 models) directly — rsil 1x10 um and
the default inductor_with_loss — pinning golden two-port
S-parameters at 5 GHz plus reciprocity/passivity shape.
"""

import importlib.util

import pytest

from ._profile import load_profile

sax_present = importlib.util.find_spec("sax") is not None
jax_present = importlib.util.find_spec("jax") is not None


def _ihp_sax_present():
    try:
        return importlib.util.find_spec("ihp.models.sax") is not None
    except (ImportError, AttributeError, ValueError):
        return False


ihp_present = _ihp_sax_present()
needs_sax = pytest.mark.skipif(
    not (sax_present and jax_present and ihp_present),
    reason="SAX proof needs sax + jax + ihp-gdsfactory==2.0.1",
)

# Goldens captured from ihp-gdsfactory 2.0.1 + sax 0.18.2, f = 5 GHz.
RSIL_S11 = 0.4117647058823529
RSIL_S21 = 0.5882352941176471
IND_S11 = complex(0.08983016235372465, 0.28593828754685535)
IND_S21 = complex(0.9101698376462753, -0.28593828754685535)


@needs_sax
def test_sax_registry_lists_ten_rf_models():
    profile = load_profile()  # RED: missing profile.yaml
    from ihp.models.sax import models

    expect = profile["variants"]["rf"]["sax_models"]
    assert sorted(models) == sorted(expect)
    assert len(models) == 10


@needs_sax
def test_rsil_s_params_at_5ghz():
    load_profile()  # RED: missing profile.yaml
    import jax.numpy as jnp

    from ihp.models.sax import rsil

    result = rsil(f=jnp.array([5e9]), width=1.0, length=10.0)
    s11 = complex(result[("o1", "o1")][0])
    s21 = complex(result[("o1", "o2")][0])
    assert s11 == pytest.approx(RSIL_S11, abs=1e-12)
    assert s21 == pytest.approx(RSIL_S21, abs=1e-12)
    assert complex(result[("o2", "o1")][0]) == pytest.approx(s21, abs=1e-12)


@needs_sax
def test_inductor_with_loss_s_params_at_5ghz():
    load_profile()  # RED: missing profile.yaml
    import jax.numpy as jnp

    from ihp.models.sax.inductors import inductor_with_loss

    result = inductor_with_loss(f=jnp.array([5e9]))
    s11 = complex(result[("o1", "o1")][0])
    s21 = complex(result[("o1", "o2")][0])
    assert s11 == pytest.approx(IND_S11, abs=1e-12)
    assert s21 == pytest.approx(IND_S21, abs=1e-12)
    power = abs(s11) ** 2 + abs(s21) ** 2
    assert power <= 1.0 + 1e-6

"""Extract parse carries `total` (ESCAPE-HARDEN MC-36 conformance).

`run_extraction` parse output joins the `{total, violations[]}`
shape every other solver parse serves: `total` is the device
inventory size (`device_count`), so cross-adapter consumers can
read the verdict size without knowing the extraction vocabulary.
"""

SPICE = """* extraction
.subckt bandgap_core_bus vdd vss out
X0 vdd net1 vss vss nfet w=2.0 l=0.5
X1 net1 out vdd vdd pfet w=4.0 l=0.5
.ends
"""


def _native(devices=True):
    return {
        "exit_code": 0,
        "stdout": "exttospice finished\n",
        "stderr": "",
        "tech": "sky130A",
        "cell": "bandgap_core_bus",
        "source": "gds",
        "ext_file": "/tmp/work/bandgap_core_bus.ext",
        "spice_file": "/tmp/work/bandgap_core_bus.spice",
        "spice_text": SPICE if devices else "* empty\n",
    }


def test_extract_parse_carries_total_matching_device_count():
    from rocket_engine.adapters.extract_magic import MagicExtractAdapter

    result = MagicExtractAdapter().parse(_native())
    assert result["device_count"] == 2
    assert result["total"] == result["device_count"] == 2

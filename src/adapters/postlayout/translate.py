"""KLT to vendor translation for the postlayout path."""

import re

from ..errors import AdapterError

_KLT_RE = re.compile(r"klt", re.IGNORECASE)
_DEVICE_RE = re.compile(r"^([XMRCL]\S*)\s+(\S+)\s+(\S+)\s+(\S+)(.*)$",
                        re.M)

_VENDOR_MAP = {
    "sky130_klt_nmos": "sky130_fd_pr__nfet_01v8",
    "sky130_klt_pmos": "sky130_fd_pr__pfet_01v8",
    "klt_nmos": "nfet_01v8",
    "klt_pmos": "pfet_01v8",
    "klt_res": "resistor",
    "klt_cap": "capacitor",
}


def is_klt_netlist(text):
    """Report whether a netlist carries klt generic devices.

    Args:
        text: Netlist text under check.

    Returns:
        True when klt markers appear, else False.
    """
    return bool(_KLT_RE.search(text or ""))


def translate_klt_netlist(text, vendor="sky130"):
    """Translate klt generic devices to vendor models.

    Args:
        text: Extracted netlist text with klt device classes.
        vendor: Vendor family the models translate to.

    Returns:
        (translated, mapping) with the translated netlist plus the
            device rename rows.

    Raises:
        AdapterError: unsupported_operation when a klt device has
            no vendor mapping — loud refusal naming the gap, never
            a silent sim_fail.
    """
    mapping = []
    out_lines = []
    for line in (text or "").splitlines():
        mapped = line
        lowered = line.lower()
        if "klt" in lowered:
            hit = None
            for klt, vend in _VENDOR_MAP.items():
                if klt in lowered:
                    hit = (klt, vend)
                    break
            if hit is None:
                raise AdapterError(
                    "unsupported_operation",
                    f"KLT device has no {vendor} vendor mapping: "
                    f"{line.strip()[:160]} (POSTLAYOUT-REAL gap).",
                )
            klt, vend = hit
            pattern = re.compile(re.escape(klt), re.IGNORECASE)
            mapped = pattern.sub(vend, line)
            mapping.append({"from": klt, "to": vend, "vendor": vendor})
        out_lines.append(mapped)
    return "\n".join(out_lines) + ("\n" if out_lines else ""), mapping

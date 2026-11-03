"""Post-layout SPICE adapter package (POSTLAYOUT lane).

`adapter.py` serves run_post_layout behind the ToolAdapter port; this
package re-exports its surface so the integrator wiring reads
`rocket_engine.adapters.postlayout`.
"""

from .adapter import OPERATION, PostLayoutAdapter, build_deck, build_provenance
from .adapter import delta_table

__all__ = [
    "OPERATION",
    "PostLayoutAdapter",
    "build_deck",
    "build_provenance",
    "delta_table",
]

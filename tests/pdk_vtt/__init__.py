"""PDK-VTT lane proof tests: pin the inventoried facts and the blocked verdict.

Upstream gvtt 0.1.0 cannot be imported under any installable gdsfactory
(see docs/pdk/vtt/report.md), so these tests assert the verified inventory
(a vendored upstream fixture + profile.yaml) rather than live behavior.
If upstream is fixed, this lane flips profile.yaml to healthy and adds
behavioral proofs; until then these tests fail loudly on silent edits.
"""

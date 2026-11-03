"""I28 ingredient-closure pins for Wave-3 editor and testbench verbs.

Pure helpers (no I/O, no logic beyond digests): every Wave-3
mutation receipt carries an ``i28`` closure pinning the consumed
revisions (entities, templates, profiles) so a replay can prove
drift instead of assuming it. Stored digests are canonical-JSON
sha1, matching the ledger content-key discipline.
"""

import copy
import hashlib
import json


def digest_mapping(mapping):
    """Digest one JSON-shaped mapping for an I28 pin.

    Args:
        mapping: JSON-shaped mapping to digest.

    Returns:
        Twelve hex characters of canonical-JSON sha1.
    """
    text = json.dumps(mapping, sort_keys=True, default=str)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def pin_entities(head, revisions):
    """Pin consumed entity revisions at one head revision.

    Args:
        head: Ledger head revision the pin rides on.
        revisions: Entity id to live entity revision mapping.

    Returns:
        Pin with head revision plus the sorted entity map.
    """
    return {
        "revision": head,
        "entities": {key: revisions[key] for key in sorted(revisions)},
    }


def pin_template(provenance):
    """Pin one template provenance into the closure.

    Args:
        provenance: Template provenance mapping (kind,
            template_version, digest).

    Returns:
        Deep copy of the provenance plus its digest pin.
    """
    kept = copy.deepcopy(dict(provenance or {}))
    kept["digest"] = kept.get("digest") or digest_mapping(kept)
    return kept


def pin_closure(head, entities=None, template=None, profile=None):
    """Assemble one I28 closure pin for a Wave-3 receipt.

    Args:
        head: Ledger head revision the pin rides on.
        entities: Entity id to live revision mapping, if any.
        template: Template provenance mapping, if consumed.
        profile: Technology profile pin ({name, version}), if
            consumed.

    Returns:
        Closure pin with revision, entity pins, template pin,
            and profile pin (each present only when consumed).
    """
    pin = {"revision": head}
    if entities:
        pin["entities"] = {
            key: entities[key] for key in sorted(entities)
        }
    if template is not None:
        pin["template"] = pin_template(template)
    if profile is not None:
        pin["profile"] = copy.deepcopy(dict(profile))
    pin["digest"] = digest_mapping(
        {key: pin[key] for key in sorted(pin) if key != "digest"}
    )
    return pin

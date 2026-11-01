#!/usr/bin/env python3
"""Validate the v1 design contract and derive its consumer types/help/examples.

This validates the proposed boundary, not current provider conformance. Use
--write to regenerate artifacts after editing the canonical contracts/v1 bundle.
The root manifest allowlists every module. No network/schema retrieval is allowed.
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts" / "engine-v1.schema.json"
OUTPUT = ROOT / "contracts" / "generated"


def read_json(path):
    """Read strict JSON without executing source or accepting non-finite values."""
    def reject(value):
        raise ValueError(f"Non-finite JSON number: {value}")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key in {path}: {key}")
            result[key] = value
        return result
    return json.loads(path.read_text(), parse_constant=reject, object_pairs_hook=unique)


def bundle_path(relative, directory):
    """Resolve only explicitly allowlisted, contained bundle paths."""
    if not isinstance(relative, str) or not re.fullmatch(
            rf"{directory}/[a-z0-9-]+(?:\.schema)?\.json", relative):
        raise ValueError(f"Non-allowlisted bundle path: {relative}")
    path = CONTRACT.parent / relative
    if not path.resolve().is_relative_to(CONTRACT.parent.resolve()):
        raise ValueError(f"Bundle path escapes contracts: {relative}")
    return path


def load_bundle():
    """Compile one canonical local bundle and construct its offline registry.

    The manifest's $defs are aliases, not copied payload definitions. Authored
    modules own each original definition exactly once. Transaction-local edit
    variants are derived in memory and written only as generated consumer output.
    """
    manifest = read_json(CONTRACT)
    root_id = manifest["$id"]
    if root_id != "urn:rocketeda:engine:v1":
        raise ValueError("Unexpected root schema identifier")
    if len(CONTRACT.read_text().splitlines()) >= 3000:
        raise ValueError("Authored root manifest exceeds size limit")
    definitions, resources, aliases = {}, {}, {}
    for item in manifest["x-schema-modules"]:
        path = bundle_path(item["path"], "v1/schemas")
        module = read_json(path)
        identifier = item["id"]
        slug = path.name.removesuffix(".schema.json")
        if identifier != root_id + ":schemas:" + slug:
            raise ValueError(f"Non-allowlisted schema ID: {identifier}")
        if module.get("$id") != identifier or identifier in resources:
            raise ValueError(f"Duplicate/mismatched module ID: {identifier}")
        for node in walk(module):
            if node is not module and "$id" in node:
                raise ValueError(f"Nested schema identifiers are not allowlisted: {path}")
            if "$dynamicRef" in node or "$recursiveRef" in node:
                raise ValueError(f"Dynamic schema retrieval is not supported: {path}")
        if len(path.read_text().splitlines()) >= 3000:
            raise ValueError(f"Authored schema module exceeds size limit: {path}")
        resources[identifier] = module
        for name, schema in module["$defs"].items():
            if name in definitions or "x-derived-from" in schema:
                raise ValueError(f"Duplicated/authored derived schema: {name}")
            definitions[name] = copy.deepcopy(schema)
            aliases[name] = {"$ref": identifier + "#/$defs/" + name}
    # All module references pass through the manifest export table. Flatten them
    # to local refs for standalone consumers; never retrieve an unknown resource.
    for schema in definitions.values():
        for node in walk(schema):
            if "$ref" in node:
                ref = node["$ref"]
                if not ref.startswith(root_id + "#/$defs/"):
                    raise ValueError(f"Module reference is not a root export: {ref}")
                node["$ref"] = ref[len(root_id):]
    expanded = {key: copy.deepcopy(value) for key, value in manifest.items()
                if key not in {"$defs", "x-schema-modules", "x-derived-schema", "x-catalog-files"}}
    expanded["description"] = (
        "Generated standalone consumer schema compiled from the canonical Engine v1 "
        "bundle rooted at contracts/engine-v1.schema.json. Do not edit generated output.")
    expanded["x-generated-from"] = "contracts/engine-v1.schema.json"
    expanded["$defs"] = definitions
    generated = edit_variants(expanded)
    definitions.update(generated)
    derived_spec = manifest["x-derived-schema"]
    derived_id = root_id + ":derived:edit-inputs"
    if derived_spec["id"] != derived_id or derived_spec["path"] != "generated/edit-inputs.schema.json":
        raise ValueError("Unexpected derived schema resource")
    derived_module = {"$schema": manifest["$schema"], "$id": derived_id,
                      "$defs": copy.deepcopy(generated)}
    for schema in derived_module["$defs"].values():
        for node in walk(schema):
            if "$ref" in node:
                node["$ref"] = root_id + node["$ref"]
    resources[derived_id] = derived_module
    aliases.update({name: {"$ref": derived_id + "#/$defs/" + name}
                    for name in generated})
    if manifest["$defs"] != aliases:
        raise ValueError("Manifest exports do not exactly match authored/derived definitions")
    expected = {"x-methods", "x-tasks", "x-tools", "x-workflows",
                "x-component-types", "x-errors", "x-examples", "x-rejections"}
    if set(manifest["x-catalog-files"]) != expected:
        raise ValueError("Missing or unexpected catalog/example manifest entries")
    for key, relative in manifest["x-catalog-files"].items():
        directory = "v1/examples" if key in {"x-examples", "x-rejections"} else "v1/catalog"
        path = bundle_path(relative, directory)
        if len(path.read_text().splitlines()) >= 3000:
            raise ValueError(f"Authored catalog/examples exceeds size limit: {path}")
        expanded[key] = read_json(path)
    def reject_retrieval(uri):
        raise ValueError(f"Schema retrieval is disabled: {uri}")
    resources[root_id] = manifest
    registry = Registry(retrieve=reject_retrieval).with_resources(
        (identifier, Resource.from_contents(value)) for identifier, value in resources.items())
    return expanded, manifest, registry, derived_module


def load_contract():
    """Return the compiled canonical contract for local tooling consumers."""
    return load_bundle()[0]


def walk(value):
    """Yield every mapping in a JSON-compatible tree."""
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def edit_variants(contract):
    """Derive transaction-local ID/reference variants from stored entity shapes.

    The original stored definitions own each field. Derived edit inputs permit
    LocalRef/EditId solely during an atomic change set. This avoids hand-kept
    copies while keeping unresolved transaction aliases out of stored records.
    """
    definitions = contract["$defs"]
    original = {k: v for k, v in definitions.items() if "x-derived-from" not in v}
    depends = {}
    def needs_variant(name, seen=None):
        if name in {"Ref", "OpaqueId"}:
            return True
        if name in {"EditRef", "EditId", "LocalRef", "PinnedRef", "WorkingRef"}:
            return False
        if name in depends:
            return depends[name]
        seen = (seen or set()) | {name}
        refs = [node["$ref"].rsplit("/", 1)[1]
                for node in walk(original[name]) if "$ref" in node]
        depends[name] = any(ref not in seen and needs_variant(ref, seen)
                            for ref in refs)
        return depends[name]
    generated = {}
    def build(name):
        if name == "Ref":
            return "EditRef"
        if name == "OpaqueId":
            return "EditId"
        if not needs_variant(name):
            return name
        new_name = "Edit" + name
        if new_name in generated:
            return new_name
        generated[new_name] = {}
        value = copy.deepcopy(original[name])
        for node in walk(value):
            if "$ref" in node:
                child = node["$ref"].rsplit("/", 1)[1]
                node["$ref"] = "#/$defs/" + build(child)
        value["x-derived-from"] = "#/$defs/" + name
        generated[new_name] = value
        return new_name
    build("EntityData")
    return generated


def validator(contract, pointer):
    """Validate a named shape using the canonical local reference registry."""
    return Draft202012Validator(
        {"$schema": contract["$schema"], "$defs": contract["$defs"], "$ref": pointer},
        format_checker=FormatChecker(),
    )


def ts(schema):
    """Derive structural TypeScript types; runtime predicates remain in schema."""
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[1]
    if "const" in schema:
        return json.dumps(schema["const"])
    if "enum" in schema:
        return " | ".join(json.dumps(item) for item in schema["enum"])
    base = None
    kind = schema.get("type")
    if isinstance(kind, list):
        base = " | ".join(ts({**schema, "type": item}) for item in kind)
    elif kind == "object" or "properties" in schema:
        required = schema.get("required", [])
        fields = [f'{json.dumps(k)}{"" if k in required else "?"}: {ts(v)};'
                  for k, v in schema.get("properties", {}).items()]
        additional = schema.get("additionalProperties", False)
        if isinstance(additional, dict):
            # Optional named fields include undefined in TypeScript. Their
            # structural types may also refine the generic map value schema.
            values = [ts(additional)]
            values.extend(ts(value) for value in schema.get("properties", {}).values())
            if any(key not in required for key in schema.get("properties", {})):
                values.append("undefined")
            fields.append(f"[key: string]: {' | '.join(dict.fromkeys(values))};")
        base = "{ " + " ".join(fields) + " }"
    elif kind == "array":
        base = f'Array<{ts(schema.get("items", {}))}>'
    elif kind in {"number", "integer"}:
        base = "number"
    elif kind in {"string", "boolean", "null"}:
        base = kind
    variants = schema.get("oneOf", schema.get("anyOf"))
    if variants:
        choice = "(" + " | ".join(ts(v) for v in variants) + ")"
        base = f"({base}) & {choice}" if base else choice
    # if/then/not, numeric limits and exact-property checks are runtime predicates.
    unconditional = [part for part in schema.get("allOf", []) if "if" not in part]
    if unconditional:
        base = " & ".join([base or "unknown", *(ts(v) for v in unconditional)])
    return base or "unknown"


def render_python(contract):
    """Derive Python consumer DTOs via the sibling boundary generator.

    Loaded by exact path: tests import this checker with
    importlib.util.spec_from_file_location, so scripts is not
    guaranteed to be on sys.path for a plain sibling import.
    """
    path = Path(__file__).with_name("schema_models.py")
    spec = importlib.util.spec_from_file_location("v1_schema_models", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.render_python(contract)


def render(contract):
    """Generate artifacts exclusively from the canonical contract."""
    definitions = contract["$defs"]
    types = ["// Generated by scripts/check_v1_contract.py --write; do not edit.",
             "// Structural types; JSON Schema owns runtime/conditional validation."]
    for name, schema in definitions.items():
        if schema.get("description"):
            desc = schema["description"].replace("*/", "* /").replace("\n", " ")
            types.append(f"/** {desc} */")
        types.append(f"export type {name} = {ts(schema)};")
    types += ["", "export interface EngineClient {"]
    for method, spec in contract["x-methods"].items():
        params = definitions[method.title() + "Request"]["properties"]["params"]["$ref"].rsplit("/", 1)[1]
        result = spec["result_schema"].rsplit("/", 1)[1]
        types.append(f"  {method}(requestId: OpaqueId, params: {params}): Promise<{result}>;")
    types.append("}")
    help_data = {"version": contract["version"], "status": contract["x-status"],
                 **{key[2:]: contract[key] for key in
                    ("x-methods", "x-tasks", "x-tools", "x-workflows", "x-component-types", "x-errors")}}
    catalog = ["# Generated v1 API catalog", "", "Generated from engine-v1.schema.json; runtime qualification is separate.",
               "", "| Method | Job | HTTP |", "|---|---|---|"]
    for name, item in contract["x-methods"].items():
        http = item["http"]
        catalog.append(f'| `{name}` | {item["description"]} | `{http["method"]} {http["path"]}` |')
    catalog += ["", "## Tool tasks", "", "Every task below has a closed options schema. Registration does not claim installed/qualified support.",
                "", "| Task | Purpose | Providers/backends |", "|---|---|---|"]
    for name, item in contract["x-tasks"].items():
        catalog.append(f'| `{name}` | {item["description"]} | {", ".join(item["tools"])} |')
    catalog += ["", "## Tools and packages", "", "| ID | Kind | Purpose |", "|---|---|---|"]
    for name, item in contract["x-tools"].items():
        catalog.append(f'| `{name}` | {item["kind"]} | {item["description"]} |')
    examples = ["# Generated contract examples", "", "Illustrative contract fixtures; these are not claimed live solver executions."]
    for item in contract["x-examples"]:
        examples += ["", "## " + item["name"], "", "Schema: `" + item["schema"] + "`", "", "```json", json.dumps(item["value"], indent=2), "```"]
    artifacts = {"engine-v1.expanded.schema.json": json.dumps(contract, indent=2) + "\n",
                 "client-types.d.ts": "\n".join(types) + "\n",
                 "help.json": json.dumps(help_data, indent=2) + "\n",
                 "CATALOG.md": "\n".join(catalog) + "\n",
                 "EXAMPLES.md": "\n".join(examples) + "\n"}
    artifacts.update(render_python(contract))
    return artifacts


def check(contract, manifest=None, registry=None):
    """Check schema safety, all fixtures, cross references and generated metadata."""
    Draft202012Validator.check_schema(contract)
    if manifest is not None:
        Draft202012Validator.check_schema(manifest)
    definitions = contract["$defs"]
    for node in walk(contract):
        if "$ref" in node:
            pointer = node["$ref"]
            if not re.fullmatch(r"#/\$defs/[A-Za-z0-9_]+", pointer):
                raise ValueError(f"Non-allowlisted schema reference: {pointer}")
            if pointer.rsplit("/", 1)[1] not in definitions:
                raise ValueError(f"Missing schema: {pointer}")
    expected_variants = edit_variants(contract)
    actual_variants = {k: v for k, v in definitions.items() if "x-derived-from" in v}
    if actual_variants != expected_variants:
        raise ValueError("Derived edit input variants are stale; use --write")
    methods = set(contract["x-methods"])
    if methods != {"describe", "query", "edit", "run", "script", "watch"}:
        raise ValueError("Unexpected public vocabulary")
    dispatch = definitions["RunStart"]
    if set(dispatch["properties"]["task"]["enum"]) != set(contract["x-tasks"]):
        raise ValueError("Task dispatch enum differs from registry")
    branches = {branch["properties"]["task"]["const"]: branch
                for branch in dispatch["oneOf"]}
    if len(branches) != len(dispatch["oneOf"]) or set(branches) != set(contract["x-tasks"]):
        raise ValueError("Task dispatch branches differ from registry")
    for name, item in contract["x-tasks"].items():
        option = item["input_schema"].rsplit("/", 1)[1]
        if definitions[option].get("additionalProperties") is not False:
            raise ValueError(f"Task has open/opaque options: {name}")
        branch = branches[name]
        properties = branch["properties"]
        if properties["options"] != {"$ref": item["input_schema"]}:
            raise ValueError(f"Task options dispatch differs from registry: {name}")
        if properties["target"]["properties"]["kind"]["enum"] != item["target_kinds"]:
            raise ValueError(f"Task target scopes differ from registry: {name}")
        if not set(item["providers"]).issubset(item["tools"]):
            raise ValueError(f"Task provider is not a declared dependency: {name}")
        if item["providers"]:
            if properties["tool"]["enum"] != item["providers"]:
                raise ValueError(f"Task provider dispatch differs from registry: {name}")
        elif branch.get("not") != {"required": ["tool"]}:
            raise ValueError(f"Engine-orchestrated task permits arbitrary driver: {name}")
        for tool in item["tools"]:
            if name not in contract["x-tools"][tool]["tasks"]:
                raise ValueError(f"Inconsistent task/tool association: {name}/{tool}")
        ports = item.get("io")
        if not isinstance(ports, dict):
            raise ValueError(f"Task lacks typed io ports: {name}")
        for direction in ("inputs", "outputs"):
            declared = ports.get(direction)
            if not isinstance(declared, list):
                raise ValueError(f"Task io.{direction} is not a port list: {name}")
            seen = set()
            for port in declared:
                if list(validator(contract, "#/$defs/TaskPort").iter_errors(port)):
                    label = port.get("name") if isinstance(port, dict) else port
                    raise ValueError(f"Task declares untyped {direction} port: {name}/{label}")
                if port["name"] in seen:
                    raise ValueError(f"Duplicate task port name: {name}/{port['name']}")
                seen.add(port["name"])
        if not ports["outputs"]:
            raise ValueError(f"Task declares no output ports: {name}")
        presentation = item.get("presentation")
        if (not isinstance(presentation, list) or not presentation
                or not set(presentation) <= {"traces", "table", "matrix", "markers",
                                             "digital", "field", "tree"}):
            raise ValueError(f"Task has unknown presentation kinds: {name}")
        if item.get("delivery") not in {"mvp", "post_mvp", "off_mvp"}:
            raise ValueError(f"Task has unknown delivery scope: {name}")
    for name, item in contract["x-tools"].items():
        for task in item["tasks"]:
            if name not in contract["x-tasks"][task]["tools"]:
                raise ValueError(f"Inconsistent tool/task association: {name}/{task}")
    for label, should_pass in [("x-examples", True), ("x-rejections", False)]:
        for item in contract[label]:
            errors = list(validator(contract, item["schema"]).iter_errors(item["value"]))
            if bool(errors) == should_pass:
                detail = errors[0].message[:500] if errors else "incorrectly accepted"
                raise ValueError(f'{item["name"]}: {detail}')
            if manifest is not None:
                external = Draft202012Validator(
                    {"$schema": manifest["$schema"],
                     "$ref": manifest["$id"] + item["schema"]},
                    registry=registry, format_checker=FormatChecker())
                external_errors = list(external.iter_errors(item["value"]))
                if bool(external_errors) == should_pass:
                    raise ValueError(f'Bundle/expanded fixture disagreement: {item["name"]}')
    covered = {item["value"]["params"]["task"] for item in contract["x-examples"]
               if item["schema"] == "#/$defs/Request"
               and item["value"].get("method") == "run"
               and item["value"]["params"].get("action") == "start"}
    missing = set(contract["x-tasks"]) - covered
    if missing:
        raise ValueError(f"Tasks lack valid request fixtures: {sorted(missing)}")
    return len(contract["x-examples"]), len(contract["x-rejections"])


def main():
    """Check boundary fixtures and generated artifacts without running providers."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    contract, manifest, registry, derived_module = load_bundle()
    positives, negatives = check(contract, manifest, registry)
    outputs = render(contract)
    outputs["edit-inputs.schema.json"] = json.dumps(derived_module, indent=2) + "\n"
    for name, content in outputs.items():
        path = OUTPUT / name
        if args.write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        elif not path.exists() or path.read_text() != content:
            raise ValueError(f"Generated artifact stale: {path.relative_to(ROOT)}")
    print(f"v1 contract valid: {len(contract['x-methods'])} methods, "
          f"{len(contract['x-tasks'])} tasks, {len(contract['x-tools'])} tools; "
          f"{positives} accepted and {negatives} rejected fixtures; generated artifacts current.")
    print("Provider/transport conformance is pending migration; no solver execution claimed.")


if __name__ == "__main__":
    main()

"""Historical v1 design-audit probe; never dispatches or opens runtime state.

Run from the audited checkout: python docs/audits/v1_baseline_probe.py
This deliberately demonstrates defects in the pinned 0.17.1 contract checker.
It is not a test asserting that these behaviors should survive a fix.
"""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
from pathlib import Path

BASELINE = "aa2697e79f181a252aff6d775e3aede07fd93248"
INVENTORY_BLOB = "af9297e4784a3674718d5cba7c078d08be891b5b"


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[2])
    args = cli.parse_args()
    path = args.source / "src/ai_orchestrator/contract_inventory.py"
    raw = path.read_bytes()
    actual = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    if actual != INVENTORY_BLOB:
        raise SystemExit("Not the audited inventory source; do not reinterpret this historical probe as a regression test")
    names = {"schema_semantics", "_cli_authority", "_cli_commands"}
    parsed = ast.parse(raw.decode("utf-8"), filename=str(path))
    selected = [n for n in parsed.body if isinstance(n, ast.FunctionDef) and n.name in names]
    if {n.name for n in selected} != names:
        raise SystemExit("Audited functions are missing")
    namespace = {"argparse": argparse}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), namespace)
    normalize = namespace["schema_semantics"]
    inventory = namespace["_cli_commands"]
    results = []

    def schema_case(name: str, left: dict, right: dict) -> None:
        if left == right:
            raise AssertionError("Probe inputs must differ")
        collision = normalize(left) == normalize(right)
        results.append({"case": name, "changed_input": True, "inventory_collision": collision})
        if not collision:
            raise AssertionError(f"Expected audited defect was not reproduced: {name}")

    for name in ("description", "title", "$comment"):
        a = {"type": "object", "properties": {name: {"type": "string"}}, "required": [name]}
        b = copy.deepcopy(a)
        b["properties"][name]["type"] = "integer"
        schema_case("property-named-" + name, a, b)
    a = {"$defs": {"description": {"type": "string"}}, "$ref": "#/$defs/description"}
    b = copy.deepcopy(a)
    b["$defs"]["description"]["type"] = "integer"
    schema_case("definition-named-description", a, b)
    for keyword in ("const", "default", "enum"):
        x, y = {"description": "no"}, {"description": "yes"}
        a = {keyword: [x] if keyword == "enum" else x}
        b = {keyword: [y] if keyword == "enum" else y}
        schema_case("literal-data-under-" + keyword, a, b)

    def parser() -> argparse.ArgumentParser:
        p = argparse.ArgumentParser()
        p.add_argument("--project", type=Path, default=Path("."))
        sub = p.add_subparsers(dest="command", required=True)
        serve = sub.add_parser("serve")
        group = serve.add_mutually_exclusive_group()
        group.add_argument("--single-terminal", dest="single_terminal", action="store_true")
        group.add_argument("--legacy-terminal", dest="single_terminal", action="store_false")
        serve.set_defaults(single_terminal=True)
        serve.add_argument("--gate-timeout", type=float, default=120)
        return p

    def serve(p):
        return next(a for a in p._actions if isinstance(a, argparse._SubParsersAction)).choices["serve"]

    def action(p, dest):
        return next(a for a in p._actions if a.dest == dest)

    for name in ("default", "type", "const", "global-option", "mutual-exclusion"):
        left, right = parser(), parser()
        node = serve(right)
        if name == "default":
            node.set_defaults(single_terminal=False)
        elif name == "type":
            action(node, "gate_timeout").type = str
        elif name == "const":
            next(a for a in node._actions if "--single-terminal" in a.option_strings).const = False
        elif name == "global-option":
            action(right, "project").required = True
        else:
            node._mutually_exclusive_groups.clear()
        collision = inventory(left) == inventory(right)
        results.append({"case": "cli-" + name, "changed_input": True, "inventory_collision": collision})
        if not collision:
            raise AssertionError(f"Expected audited defect was not reproduced: {name}")

    print(json.dumps({"baseline_commit": BASELINE, "inventory_blob": actual,
                      "scope": "exact source functions; synthetic schemas/parsers; no application runtime or provider calls",
                      "result": "BASELINE_GAPS_REPRODUCED", "cases": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

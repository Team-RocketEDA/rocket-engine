#!/usr/bin/env python3
"""Sprint kanban for the engine MVP: one markdown board, ticket statuses.

Board lives at docs/sprint-board.md (repo root = parent of scripts/).
Ticket line format: ``- [ID] Title`` under ``## Backlog|Ready|Doing|Review|Done``.
Long descriptions live in docs/tickets/<ID>.md (managed, never hand-parsed).

Usage:
    python scripts/sprint.py list [status]
    python scripts/sprint.py show <id>
    python scripts/sprint.py add "title" [--id ID] [--status backlog] [--body FILE]
    python scripts/sprint.py describe <id> <file>
    python scripts/sprint.py undescribe <id>
    python scripts/sprint.py move <id> <status>
    python scripts/sprint.py remove <id>
"""

import argparse
import re
import shutil
import sys
from pathlib import Path

BOARD = Path(__file__).resolve().parent.parent / "docs" / "sprint-board.md"
TICKETS_DIR = Path(__file__).resolve().parent.parent / "docs" / "tickets"
SECTIONS = ["Backlog", "Ready", "Doing", "Review", "Done"]
ALIASES = {"todo": "Backlog", "do": "Doing", "doing": "Doing",
           "in-review": "Review", "done": "Done", "backlog": "Backlog",
           "ready": "Ready", "review": "Review"}
TICKET = re.compile(r"^- \[([A-Za-z0-9][\w-]*)\]\s+(.*)$")
HEADER = re.compile(r"^## (Backlog|Ready|Doing|Review|Done)\s*$")


def load():
    lines = BOARD.read_text().splitlines()
    tickets, section, index = {}, None, {}
    for num, line in enumerate(lines):
        head = HEADER.match(line)
        if head:
            section = head.group(1)
            continue
        found = TICKET.match(line)
        if found and section:
            tid, title = found.group(1), found.group(2)
            tickets[tid] = (section, title, num)
            index.setdefault(section, []).append(tid)
    return lines, tickets, index


def save(lines):
    BOARD.write_text("\n".join(lines).rstrip("\n") + "\n")


def cmd_list(args):
    _, tickets, _ = load()
    want = [ALIASES[args.status.lower()]] if args.status else SECTIONS
    if args.status and args.status.lower() not in ALIASES:
        return f"unknown status: {args.status} (want one of: backlog ready doing review done)"
    out = []
    for section in want:
        out.append(f"## {section}")
        names = [t for t, (s, _, _) in tickets.items() if s == section]
        if names:
            out.extend(f"- [{t}] {tickets[t][1]}" for t in names)
        else:
            out.append("(empty)")
    return "\n".join(out)


def body_path(tid):
    return TICKETS_DIR / f"{tid}.md"


def attach_body(tid, src):
    src = Path(src)
    if not src.is_file():
        return None
    TICKETS_DIR.mkdir(parents=True, exist_ok=True)
    dest = body_path(tid)
    shutil.copy(src, dest)
    return dest


def cmd_show(args):
    _, tickets, _ = load()
    if args.id not in tickets:
        return f"unknown ticket: {args.id}"
    section, title, _ = tickets[args.id]
    head = f"[{args.id}] {title}\nstatus: {section}"
    dest = body_path(args.id)
    if dest.is_file():
        return f"{head}\n---\n{dest.read_text().rstrip()}"
    return f"{head}\n(no description)"


def cmd_add(args):
    lines, tickets, _ = load()
    section = ALIASES.get(args.status.lower())
    if section is None:
        return f"unknown status: {args.status}"
    tid = args.id
    if tid is None:
        used = {int(t[1:]) for t in tickets if re.fullmatch(r"T\d+", t)}
        tid = f"T{(max(used) + 1) if used else 1}"
    if tid in tickets:
        return f"duplicate ticket: {tid}"
    if not re.fullmatch(r"[A-Za-z0-9][\w-]*", tid):
        return f"bad id (letters/digits/_/-): {tid}"
    if getattr(args, "body", None) and not Path(args.body).is_file():
        return f"no such body file: {args.body}"
    target = f"## {section}"
    at = next(i for i, line in enumerate(lines) if line.strip() == target)
    insert = at + 1
    while insert < len(lines) and not lines[insert].startswith("## "):
        insert += 1
    lines.insert(insert, f"- [{tid}] {args.title}")
    save(lines)
    if getattr(args, "body", None):
        attach_body(tid, args.body)
        return f"added [{tid}] to {section} (+ description)"
    return f"added [{tid}] to {section}"


def cmd_move(args):
    lines, tickets, _ = load()
    section = ALIASES.get(args.status.lower())
    if section is None:
        return f"unknown status: {args.status}"
    if args.id not in tickets:
        return f"unknown ticket: {args.id}"
    _, title, num = tickets[args.id]
    del lines[num]
    target = f"## {section}"
    at = next(i for i, line in enumerate(lines) if line.strip() == target)
    insert = at + 1
    while insert < len(lines) and not lines[insert].startswith("## "):
        insert += 1
    lines.insert(insert, f"- [{args.id}] {title}")
    save(lines)
    return f"moved [{args.id}] to {section}"


def cmd_describe(args):
    _, tickets, _ = load()
    if args.id not in tickets:
        return f"unknown ticket: {args.id}"
    if attach_body(args.id, args.file) is None:
        return f"no such body file: {args.file}"
    return f"described [{args.id}]"


def cmd_undescribe(args):
    _, tickets, _ = load()
    if args.id not in tickets:
        return f"unknown ticket: {args.id}"
    dest = body_path(args.id)
    if not dest.is_file():
        return f"no description for [{args.id}]"
    dest.unlink()
    return f"undescribed [{args.id}]"


def cmd_remove(args):
    lines, tickets, _ = load()
    if args.id not in tickets:
        return f"unknown ticket: {args.id}"
    del lines[tickets[args.id][2]]
    save(lines)
    dest = body_path(args.id)
    if dest.is_file():
        dest.unlink()
        return f"removed [{args.id}] (+ description)"
    return f"removed [{args.id}]"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Sprint kanban board.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list", help="show tickets, optionally one status")
    p.add_argument("status", nargs="?")
    p = sub.add_parser("show", help="show one ticket")
    p.add_argument("id")
    p = sub.add_parser("add", help="add a ticket to a status")
    p.add_argument("title")
    p.add_argument("--id")
    p.add_argument("--status", default="backlog")
    p.add_argument("--body", default=None)
    p = sub.add_parser("describe", help="attach a description file to a ticket")
    p.add_argument("id")
    p.add_argument("file")
    p = sub.add_parser("undescribe", help="remove a ticket description")
    p.add_argument("id")
    p = sub.add_parser("move", help="move a ticket to a status")
    p.add_argument("id")
    p.add_argument("status")
    p = sub.add_parser("remove", help="remove a ticket from the board")
    p.add_argument("id")
    args = parser.parse_args(argv)
    print({"list": cmd_list, "show": cmd_show, "add": cmd_add,
           "describe": cmd_describe, "undescribe": cmd_undescribe,
           "move": cmd_move, "remove": cmd_remove}[args.cmd](args))


if __name__ == "__main__":
    main()

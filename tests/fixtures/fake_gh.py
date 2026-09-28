#!/usr/bin/env python3
"""A stand-in for the gh command, for tests/test_report.py. It records every call (arguments and
stdin) in $FAKE_GH_LOG and keeps issues in $FAKE_GH_STATE, supporting only the issue commands
scraper/report.py uses. It never touches the network."""
import json, os, sys

args = sys.argv[1:]
stdin = sys.stdin.read() if "-" in args else ""
with open(os.environ["FAKE_GH_LOG"], "a") as f:
    f.write(json.dumps({"args": args, "stdin": stdin}) + "\n")
path = os.environ["FAKE_GH_STATE"]
state = json.load(open(path)) if os.path.exists(path) else {"issues": []}
issues = state["issues"]
opt = lambda name: args[args.index(name) + 1] if name in args else None
find = lambda: next(i for i in issues if str(i["number"]) == args[2])

if args[:2] == ["issue", "list"]:
    fields = opt("--json").split(",")
    print(json.dumps([{k: i[k] for k in fields} for i in issues]))
elif args[:2] == ["issue", "create"]:
    n = max([i["number"] for i in issues] + [0]) + 1
    issues.append({"number": n, "title": opt("--title"), "state": "OPEN", "body": stdin, "comments": [],
                   "author": {"login": "app/github-actions", "is_bot": True}})
    print(f"https://github.com/{opt('--repo')}/issues/{n}")
elif args[:2] == ["issue", "edit"]:
    find()["body"] = stdin
elif args[:2] == ["issue", "comment"]:
    find()["comments"].append(stdin)
elif args[:2] == ["issue", "close"]:
    find()["state"] = "CLOSED"
elif args[:2] == ["issue", "reopen"]:
    find()["state"] = "OPEN"
else:
    sys.exit(f"fake gh: unsupported {args}")
json.dump(state, open(path, "w"))

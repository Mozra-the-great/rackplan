"""Sync .github/labels.json to the repository's labels (standard library only).

Additive: creates missing labels and updates color/description of existing ones.
Never deletes a label and never touches how labels are assigned to issues.

Usage: GH_TOKEN=... REPO=owner/name python3 scripts/sync_labels.py [--dry-run]
"""
import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

CONFIG = pathlib.Path(__file__).resolve().parent.parent / ".github" / "labels.json"
API = "https://api.github.com"


def plan_sync(existing, wanted):
    """Return a list of ('create' | 'update', label) actions.

    `existing` maps label name -> {"color", "description"} as returned by the API;
    names match case-insensitively, like on GitHub.
    """
    have = {name.lower(): data for name, data in existing.items()}
    actions = []
    for label in wanted:
        current = have.get(label["name"].lower())
        if current is None:
            actions.append(("create", label))
        elif (
            (current.get("color") or "").lower() != label["color"].lower()
            or (current.get("description") or "") != label["description"]
        ):
            actions.append(("update", label))
    return actions


def validate_config(config):
    seen = set()
    for label in config["labels"]:
        name = label["name"]
        if name.lower() in seen:
            raise ValueError(f"duplicate label: {name}")
        seen.add(name.lower())
        color = label["color"]
        if len(color) != 6 or any(ch not in "0123456789abcdefABCDEF" for ch in color):
            raise ValueError(f"bad color for {name}: {color}")
        if len(label["description"]) > 100:
            raise ValueError(f"description of {name} exceeds 100 characters")


def call(method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(API + path, data=data, method=method)
    req.add_header("Authorization", "Bearer " + os.environ["GH_TOKEN"])
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as err:
        print(err.read().decode(), file=sys.stderr)
        raise


def existing_labels(repo):
    labels = {}
    page = 1
    while True:
        batch = call("GET", f"/repos/{repo}/labels?per_page=100&page={page}")
        if not batch:
            return labels
        for item in batch:
            labels[item["name"]] = item
        page += 1


def main(argv):
    dry_run = "--dry-run" in argv
    repo = os.environ["REPO"]
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    validate_config(config)
    actions = plan_sync(existing_labels(repo), config["labels"])
    for action, label in actions:
        print(f"{action}: {label['name']}")
        if dry_run:
            continue
        body = {"color": label["color"], "description": label["description"]}
        if action == "create":
            call("POST", f"/repos/{repo}/labels", {"name": label["name"], **body})
        else:
            name = urllib.parse.quote(label["name"], safe="")
            call("PATCH", f"/repos/{repo}/labels/{name}", body)
    print(f"{len(actions)} change(s), {len(config['labels'])} labels in config")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

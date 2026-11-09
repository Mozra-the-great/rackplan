"""Temporary helper: create one catalogue issue per brand. Idempotent (skips existing titles)."""
import json
import os
import sys
import time
import urllib.error
import urllib.request

API = "https://api.github.com"
REPO = os.environ["REPO"]
TOKEN = os.environ["GH_TOKEN"]
PAUSE = 1.5


def call(method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    for attempt in range(8):
        req = urllib.request.Request(API + path, data=data, method=method)
        req.add_header("Authorization", "Bearer " + TOKEN)
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as err:
            if err.code in (403, 429) or err.code >= 500:
                wait = int(err.headers.get("Retry-After") or 60 * (attempt + 1))
                print(f"HTTP {err.code}, waiting {wait}s", flush=True)
                time.sleep(wait)
                continue
            print(err.read().decode(), file=sys.stderr)
            raise
    raise RuntimeError("giving up after repeated rate limits")


def existing_titles():
    titles = set()
    page = 1
    while True:
        batch = call("GET", f"/repos/{REPO}/issues?state=all&per_page=100&page={page}")
        if not batch:
            return titles
        titles.update(i["title"] for i in batch if "pull_request" not in i)
        page += 1


def build_body(brand):
    cats = brand["categories"]
    record = json.dumps(brand, ensure_ascii=False)
    parent = f", sub-brand of `{brand['parent']}`" if "parent" in brand else ""
    if len(cats) > 1:
        scope = f" for every category of the brand ({', '.join(cats)}); check manufacturer pages and datasheets."
    else:
        scope = " (check manufacturer pages and datasheets)."
    i = brand["id"]
    return (
        f"**Goal.** Add the 19-inch rack devices of **{brand['name']}** (`{i}`{parent}) to the device catalogue.\n\n"
        f"**Brand record** (`data/brands/brands.jsonl`)\n```json\n{record}\n```\n\n"
        "**Tasks**\n"
        f"- [ ] Collect the rack-mountable product lines{scope}\n"
        "- [ ] For each model record `id`, `model`, `category`, `height_u`, `width`, `depth_mm`, `weight_kg`, "
        "`power_w`, `mounting` and a `source` URL, as specified in D-01.\n"
        f"- [ ] Write `data/devices/{i}.jsonl` (sorted, fixed field order) via the tooling from D-04.\n"
        "- [ ] Run `python3 scripts/validate_devices.py` and `python3 scripts/validate_brands.py`.\n\n"
        "**Acceptance criteria**\n"
        "- [ ] Every device has a `source` and passes the validator; no values are guessed "
        "(missing data is omitted, not zero).\n"
        "- [ ] The brand's main rack lines are covered, or the gaps are listed in the PR description.\n\n"
        "**Depends on:** #11 (D-01), #13 (D-03)\n"
        "**Spec:** `CLAUDE.md` (Data model)\n\n"
        f"Plan ID: `B-{i}`"
    )


def main():
    done = existing_titles()
    created = skipped = 0
    with open("data/brands/brands.jsonl", encoding="utf-8") as fh:
        brands = [json.loads(line) for line in fh if line.strip()]
    for brand in brands:
        title = f"B-{brand['id']}: {brand['name']}: device catalogue"
        if title in done:
            skipped += 1
            continue
        labels = ["enhancement", "area/data"] + [f"cat/{c}" for c in brand["categories"]]
        call("POST", f"/repos/{REPO}/issues", {"title": title, "body": build_body(brand), "labels": labels})
        created += 1
        print(f"created {title}", flush=True)
        time.sleep(PAUSE)
    print(f"done: created={created} skipped={skipped} total={len(brands)}")


if __name__ == "__main__":
    main()

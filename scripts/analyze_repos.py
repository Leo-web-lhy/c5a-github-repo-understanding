# -*- coding: utf-8 -*-
"""Collect real GitHub repository facts through the REST API.

Console output is ASCII-only (Windows + non-ASCII console crashes this host).
Per-repo JSON and a UTF-8 log land under C5A/data and C5A/data/analyze.log.
"""
import argparse
import base64
import io
import json
import os
import statistics
import sys
import time
import traceback
import urllib.error
import urllib.request

API = "https://api.github.com"
DEFAULT_REPOS = ["psf/requests", "pallets/flask", "sindresorhus/awesome", "octocat/Hello-World"]

WATCH_MARKERS = [
    "README.md", "LICENSE", "LICENSE.txt", "CONTRIBUTING.md", "CODE_OF_CONDUCT.md",
    ".github", ".gitignore", ".editorconfig", "pyproject.toml", "setup.py",
    "setup.cfg", "requirements.txt", "tox.ini", "Makefile", "CHANGELOG.md",
    "docs", "tests", "test", "src", "AUTHORS.md", "MANIFEST.in",
]


def make_requester(token, log):
    state = {"remaining": None}

    def req(path):
        url = API + path
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "c5a-repo-analysis"}
        if token:
            headers["Authorization"] = "token " + token
        r = urllib.request.Request(url, headers=headers)
        for attempt in range(3):
            try:
                with urllib.request.urlopen(r, timeout=60) as resp:
                    if resp.headers.get("X-RateLimit-Remaining"):
                        state["remaining"] = resp.headers.get("X-RateLimit-Remaining")
                    raw = resp.read().decode("utf-8", "replace")
                    return resp.status, (json.loads(raw) if raw.strip() else {})
            except urllib.error.HTTPError as e:
                raw = e.read().decode("utf-8", "replace")
                if e.code in (403, 429) and attempt < 2:
                    log("RATE_LIMIT status=%s retry=%d" % (e.code, attempt + 1))
                    time.sleep(3 * (attempt + 1))
                    continue
                try:
                    payload = json.loads(raw) if raw.strip() else {}
                except Exception:
                    payload = {"raw": raw[:200]}
                return e.code, payload
            except Exception as exc:
                if attempt < 2:
                    log("RETRY path=%s err=%s" % (path, type(exc).__name__))
                    time.sleep(2)
                    continue
                return 0, {"error": type(exc).__name__}
        return 0, {"error": "exhausted"}

    req.state = state
    return req


def ext_of(path):
    base = path.rsplit("/", 1)[-1]
    if "." not in base:
        return "(no-ext)"
    return "." + base.rsplit(".", 1)[-1].lower()


def analyze(full, req, log):
    out = {"repo": full, "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    st, meta = req("/repos/" + full)
    log("GET /repos/%s -> %s" % (full, st))
    if st != 200:
        out["error"] = "repos status %s" % st
        return out

    branch = meta.get("default_branch") or "main"
    out["meta"] = {
        "full_name": meta.get("full_name"),
        "description": meta.get("description"),
        "html_url": meta.get("html_url"),
        "default_branch": branch,
        "size_kb": meta.get("size"),
        "stars": meta.get("stargazers_count"),
        "forks": meta.get("forks_count"),
        "watchers": meta.get("subscribers_count"),
        "open_issues": meta.get("open_issues_count"),
        "language": meta.get("language"),
        "topics": meta.get("topics") or [],
        "license": (meta.get("license") or {}).get("spdx_id"),
        "created_at": meta.get("created_at"),
        "pushed_at": meta.get("pushed_at"),
        "archived": meta.get("archived"),
        "has_issues": meta.get("has_issues"),
        "has_wiki": meta.get("has_wiki"),
        "has_projects": meta.get("has_projects"),
        "allow_squash_merge": meta.get("allow_squash_merge"),
        "allow_merge_commit": meta.get("allow_merge_commit"),
        "allow_rebase_merge": meta.get("allow_rebase_merge"),
        "delete_branch_on_merge": meta.get("delete_branch_on_merge"),
    }

    st, root = req("/repos/%s/contents/" % full)
    if isinstance(root, list):
        out["root_entries"] = [
            {"name": c.get("name"), "type": c.get("type"), "size": c.get("size")}
            for c in root
        ]
        names = [c.get("name") for c in root]
        out["markers"] = {m: (m in names) for m in WATCH_MARKERS}
    else:
        out["root_entries"] = []
        out["markers"] = {}
        log("contents/ status=%s" % st)

    st, tree = req("/repos/%s/git/trees/%s?recursive=1" % (full, branch))
    files, dirs = [], []
    if st == 200 and isinstance(tree.get("tree"), list):
        out["tree_truncated"] = bool(tree.get("truncated"))
        for node in tree["tree"]:
            if node.get("type") == "blob":
                files.append(node.get("path"))
            elif node.get("type") == "tree":
                dirs.append(node.get("path"))
        log("tree ok blobs=%d trees=%d truncated=%s"
            % (len(files), len(dirs), out["tree_truncated"]))
    else:
        out["tree_truncated"] = None
        log("tree status=%s" % st)

    out["blob_count"] = len(files)
    out["dir_count"] = len(dirs)
    exts = {}
    for p in files:
        e = ext_of(p)
        exts[e] = exts.get(e, 0) + 1
    out["top_extensions"] = sorted(exts.items(), key=lambda kv: -kv[1])[:8]
    toplevel = {}
    for p in files:
        head = p.split("/", 1)[0] if "/" in p else "(root files)"
        toplevel[head] = toplevel.get(head, 0) + 1
    out["files_per_toplevel"] = sorted(toplevel.items(), key=lambda kv: -kv[1])[:12]
    out["deepest_path_depth"] = max([p.count("/") + 1 for p in files], default=0)
    flows = [p for p in files if p.startswith(".github/workflows/")]
    out["workflow_files"] = flows

    st, commits = req("/repos/%s/commits?per_page=30&sha=%s" % (full, branch))
    commit_rows = []
    if st == 200 and isinstance(commits, list):
        for c in commits:
            msg = ((c.get("commit") or {}).get("message") or "")
            author = (c.get("author") or {}).get("login") or ((c.get("commit") or {}).get("author") or {}).get("name")
            commit_rows.append({
                "sha": c.get("sha"),
                "author": author,
                "date": ((c.get("commit") or {}).get("author") or {}).get("date"),
                "first_line": msg.split("\n")[0][:110],
                "msg_len": len(msg),
                "merge_pr": "Merge pull request #" in msg,
            })
    out["recent_commits"] = commit_rows
    out["commit_sample"] = len(commit_rows)
    if commit_rows:
        lengths = [c["msg_len"] for c in commit_rows]
        out["commit_stats"] = {
            "avg_msg_len": round(statistics.mean(lengths), 1),
            "min_msg_len": min(lengths),
            "max_msg_len": max(lengths),
            "distinct_authors": len({c["author"] for c in commit_rows}),
            "merge_pr_ratio": round(sum(1 for c in commit_rows if c["merge_pr"]) / len(commit_rows), 3),
            "oldest_in_sample": commit_rows[-1]["date"],
            "newest_in_sample": commit_rows[0]["date"],
        }

    st, branches = req("/repos/%s/branches?per_page=100" % full)
    out["branch_count_sampled"] = len(branches) if isinstance(branches, list) else None
    st, tags = req("/repos/%s/tags?per_page=100" % full)
    out["tag_count_sampled"] = len(tags) if isinstance(tags, list) else None
    st, rels = req("/repos/%s/releases?per_page=5" % full)
    if isinstance(rels, list):
        out["releases_sampled"] = [{"tag": r.get("tag_name"), "published_at": r.get("published_at")} for r in rels]

    for label, q in (
        ("prs_open", "type:pr+is:open"),
        ("prs_merged", "type:pr+is:merged"),
        ("prs_closed_unmerged", "type:pr+is:unmerged+is:closed"),
        ("issues_open", "type:issue+is:open"),
        ("issues_closed", "type:issue+is:closed"),
    ):
        st, res = req("/search/issues?q=repo:%s+%s&per_page=1" % (full, q))
        out[label] = res.get("total_count") if isinstance(res, dict) and st == 200 else None

    st, langs = req("/repos/%s/languages" % full)
    if isinstance(langs, dict) and st == 200:
        total = sum(v for v in langs.values() if isinstance(v, int)) or 1
        out["languages"] = [
            {"lang": k, "pct": round(100.0 * v / total, 1)}
            for k, v in sorted(langs.items(), key=lambda kv: -kv[1])[:5]
        ]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token-file", default="")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--repos", default="")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    logf = io.open(os.path.join(args.out_dir, "analyze.log"), "w", encoding="utf-8")

    def log(msg):
        logf.write(str(msg) + "\n")
        logf.flush()
        sys.stdout.write(str(msg).encode("ascii", "replace").decode("ascii") + "\n")
        sys.stdout.flush()

    token = ""
    if args.token_file and os.path.exists(args.token_file):
        token = io.open(args.token_file, "r", encoding="utf-8").read().strip()
    log("token_present=%s token_len=%d" % (bool(token), len(token)))

    repos = [r.strip() for r in args.repos.split(",") if r.strip()] or DEFAULT_REPOS
    req = make_requester(token, log)
    results = []
    for full in repos:
        try:
            results.append(analyze(full, req, log))
        except Exception:
            log("EXCEPTION repo=%s\n%s" % (full, traceback.format_exc()))
            results.append({"repo": full, "error": "exception"})
        time.sleep(0.4)

    with io.open(os.path.join(args.out_dir, "repos.json"), "w", encoding="utf-8") as f:
        f.write(json.dumps(results, ensure_ascii=False, indent=2))

    ok = [r for r in results if "meta" in r]
    log("SUMMARY ok=%d total=%d rate_remaining=%s"
        % (len(ok), len(results), req.state.get("remaining")))
    for r in ok:
        m = r["meta"]
        log("  %-24s blobs=%-5s depth=%-2s commits_sampled=%-3s stars=%s"
            % (m["full_name"], r.get("blob_count"), r.get("deepest_path_depth"),
               r.get("commit_sample"), m["stars"]))
    logf.close()
    return 0


if __name__ == "__main__":
    try:
        rc = main()
    except Exception:
        sys.stdout.write("FATAL\n")
        rc = 2
    sys.exit(rc)

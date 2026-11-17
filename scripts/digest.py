# -*- coding: utf-8 -*-
"""Turn data/repos.json into a readable digest (UTF-8 file; console stays ASCII)."""
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")


def main():
    with io.open(os.path.join(DATA, "repos.json"), "r", encoding="utf-8") as f:
        repos = json.load(f)

    out = []
    w = out.append
    for r in repos:
        w("\n## %s" % r.get("repo"))
        if "meta" not in r:
            w("- ERROR: %s" % r.get("error"))
            continue
        m = r["meta"]
        w("fetched_at=%s origin=%s branch=%s license=%s lang=%s size_kb=%s"
          % (r.get("fetched_at"), m["html_url"], m["default_branch"], m["license"],
             m["language"], m["size_kb"]))
        w("stars=%s forks=%s watchers=%s open_issues=%s created=%s pushed=%s archived=%s"
          % (m["stars"], m["forks"], m["watchers"], m["open_issues"], m["created_at"],
             m["pushed_at"], m["archived"]))
        w("merge_opts: squash=%s merge_commit=%s rebase=%s delete_branch_on_merge=%s"
          % (m["allow_squash_merge"], m["allow_merge_commit"], m["allow_rebase_merge"],
             m["delete_branch_on_merge"]))
        w("topics=%s" % (",".join(m["topics"]) or "-"))
        w("blobs=%s dirs=%s depth=%s tree_truncated=%s"
          % (r.get("blob_count"), r.get("dir_count"), r.get("deepest_path_depth"),
             r.get("tree_truncated")))
        w("root_entries: " + " | ".join(
            "%s(%s,%s)" % (e["name"], e["type"], e["size"]) for e in r.get("root_entries", [])))
        mk = r.get("markers") or {}
        present = [k for k, v in mk.items() if v]
        absent = [k for k, v in mk.items() if not v]
        w("markers_present: " + ", ".join(present))
        w("markers_absent: " + ", ".join(absent))
        w("top_ext: " + ", ".join("%s=%s" % (e, c) for e, c in r.get("top_extensions", [])))
        w("files_per_toplevel: " + ", ".join("%s=%s" % (d, c) for d, c in r.get("files_per_toplevel", [])))
        w("workflows(%d): %s" % (len(r.get("workflow_files", [])), ", ".join(r.get("workflow_files", []))))
        w("languages: " + ", ".join("%s %.1f%%" % (x["lang"], x["pct"]) for x in r.get("languages", [])))
        cs = r.get("commit_stats") or {}
        w("commits_sampled=%s avg_msg_len=%s min=%s max=%s authors=%s merge_pr_ratio=%s window=%s..%s"
          % (r.get("commit_sample"), cs.get("avg_msg_len"), cs.get("min_msg_len"),
             cs.get("max_msg_len"), cs.get("distinct_authors"), cs.get("merge_pr_ratio"),
             cs.get("oldest_in_sample"), cs.get("newest_in_sample")))
        w("branches_sampled=%s tags_sampled=%s releases=%s"
          % (r.get("branch_count_sampled"), r.get("tag_count_sampled"),
             [(x["tag"], (x["published_at"] or "")[:10]) for x in (r.get("releases_sampled") or [])]))
        w("prs: open=%s merged=%s closed_unmerged=%s | issues: open=%s closed=%s"
          % (r.get("prs_open"), r.get("prs_merged"), r.get("prs_closed_unmerged"),
             r.get("issues_open"), r.get("issues_closed")))
        w("recent_commits:")
        for c in r.get("recent_commits", [])[:8]:
            w("  %s %s %s len=%s merge=%s | %s"
              % (c["sha"][:8], (c["date"] or "")[:19], c["author"], c["msg_len"],
                 c["merge_pr"], c["first_line"]))

    path = os.path.join(DATA, "digest.md")
    with io.open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    sys.stdout.write("DIGEST_OK lines=%d path=%s\n" % (len(out), path))
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Copy branches/tags in both directions without forced updates or deletions."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import tempfile


def git(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, text=True, encoding="utf-8",
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout


def inventory(url: str) -> dict[str, str]:
    return {ref: sha
            for line in git("ls-remote", "--refs", "--heads", "--tags", url).splitlines()
            for sha, ref in [line.split()]}


def fetched_refs(repo: Path, host: str) -> dict[str, str]:
    roots = {f"refs/sync/{host}/heads/": "refs/heads/",
             f"refs/sync/{host}/tags/": "refs/tags/"}
    result = {}
    for line in git("for-each-ref", "--format=%(objectname) %(refname)",
                    *roots, cwd=repo).splitlines():
        sha, ref = line.split()
        for root, prefix in roots.items():
            if ref.startswith(root):
                result[prefix + ref[len(root):]] = sha
    return result


def ancestor(repo: Path, older: str, newer: str) -> bool:
    result = subprocess.run(["git", "merge-base", "--is-ancestor", older, newer],
                            cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip())
    return result.returncode == 0


def synchronize(github: str, gitverse: str, *, dry_run: bool = False,
                work_dir: Path | None = None) -> dict:
    urls = {"github": github, "gitverse": gitverse}
    report = {"time_utc": datetime.now(timezone.utc).isoformat(), "dry_run": dry_run,
              "updates": [], "conflicts": [], "errors": []}
    try:
        before = {host: inventory(url) for host, url in urls.items()}
        if before["github"] == before["gitverse"]:
            report.update(status="up_to_date", refs_equal=True)
            return report
        with tempfile.TemporaryDirectory(prefix="git-host-sync-", dir=work_dir) as temporary:
            repo = Path(temporary) / "mirror.git"
            empty_template = Path(temporary) / "empty-template"
            empty_template.mkdir()
            git("init", "--bare", "--quiet", f"--template={empty_template}", str(repo))
            hooks = Path(temporary) / "empty-hooks"
            hooks.mkdir()
            git("config", "core.hooksPath", str(hooks), cwd=repo)
            refs = {}
            for host, url in urls.items():
                git("fetch", "--quiet", "--no-tags", "--no-write-fetch-head", url,
                    f"+refs/heads/*:refs/sync/{host}/heads/*",
                    f"+refs/tags/*:refs/sync/{host}/tags/*", cwd=repo)
                refs[host] = fetched_refs(repo, host)
            for ref in sorted(refs["github"].keys() | refs["gitverse"].keys()):
                gh, gv = refs["github"].get(ref), refs["gitverse"].get(ref)
                if gh == gv:
                    continue
                if gh is None:
                    source, target, sha = "gitverse", "github", gv
                elif gv is None:
                    source, target, sha = "github", "gitverse", gh
                elif ref.startswith("refs/tags/"):
                    report["conflicts"].append(dict(ref=ref, github=gh, gitverse=gv,
                                                    reason="different_tag"))
                    continue
                elif ancestor(repo, gh, gv):
                    source, target, sha = "gitverse", "github", gv
                elif ancestor(repo, gv, gh):
                    source, target, sha = "github", "gitverse", gh
                else:
                    report["conflicts"].append(dict(ref=ref, github=gh, gitverse=gv,
                                                    reason="divergent_history"))
                    continue
                report["updates"].append(dict(ref=ref, source=source, target=target, sha=sha))
            if not dry_run:
                for target, url in urls.items():
                    updates = [item for item in report["updates"] if item["target"] == target]
                    if updates:
                        # Atomic non-force pushes reject concurrent divergence too.
                        git("push", "--atomic", "--porcelain", url,
                            *(f"{item['sha']}:{item['ref']}" for item in updates), cwd=repo)
                after = {host: inventory(url) for host, url in urls.items()}
                report["refs_equal"] = after["github"] == after["gitverse"]
                if not report["refs_equal"] and not report["conflicts"]:
                    report["errors"].append("Remote refs changed during synchronization; retry.")
        report["status"] = ("conflict" if report["conflicts"] else
                            "failed" if report["errors"] else
                            "dry_run" if dry_run else "synchronized")
    except (RuntimeError, OSError) as failure:
        report["errors"].append(str(failure))
        report["status"] = "failed"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--github", required=True)
    parser.add_argument("--gitverse", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = synchronize(args.github, args.gitverse, dry_run=args.dry_run, work_dir=args.work_dir)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered + "\n", encoding="utf-8")
    return int(report["status"] in ("conflict", "failed"))


if __name__ == "__main__":
    raise SystemExit(main())

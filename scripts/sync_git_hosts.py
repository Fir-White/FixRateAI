"""Copy branches/tags in both directions without forced updates or deletions."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time


READ_ATTEMPTS = 3
READ_BACKOFF_SECONDS = (2, 5)


def safe_error(message: str) -> str:
    """Never include URL credentials in an Actions report or retry record."""
    message = re.sub(r"(https?://)[^\s/@]+(?::[^\s/@]*)?@", r"\1[redacted]@", message)
    return re.sub(r"(?i)([?&](?:access_token|token|key)=)[^&\s]+", r"\1[redacted]", message)


class RemoteOperationError(RuntimeError):
    def __init__(self, host: str, operation: str, attempts: int, message: str):
        self.details = dict(host=host, operation=operation, attempts=attempts,
                            error=safe_error(message))
        super().__init__(f"{host}/{operation} failed after {attempts} attempt(s): {self.details['error']}")


def transient_read_failure(host: str, message: str) -> bool:
    message = message.lower()
    if any(marker in message for marker in (
            "authentication failed", "permission denied", "repository not found",
            "access denied", "could not read username", "host key verification failed",
            "certificate problem", "remote host identification has changed")):
        return False
    # GitVerse occasionally denies a smart-HTTP read with this exact RPC error.
    # It is not proof of an expired token: the same unchanged credentials have
    # completed later jobs. Retry only this read signature, never arbitrary 403s.
    if host == "gitverse" and "rpc failed" in message and "http 403" in message and "expected flush after ref listing" in message:
        return True
    if re.search(r"(?:http |returned error: |error: )(?:408|429|500|502|503|504)\b", message):
        return True
    return any(marker in message for marker in (
        "could not resolve host", "could not resolve hostname", "couldn't connect",
        "could not connect", "failed to connect", "connection timed out",
        "connection reset", "connection was reset", "remote end hung up unexpectedly",
        "temporary failure in name resolution", "tls connection was non-properly terminated",
        "empty reply from server", "git command timed out",
    ))


def remote_read(report: dict, host: str, operation: str, action):
    for attempt in range(1, READ_ATTEMPTS + 1):
        try:
            return action()
        except (RuntimeError, OSError) as failure:
            error = safe_error(str(failure))
            if attempt == READ_ATTEMPTS or not transient_read_failure(host, error):
                raise RemoteOperationError(host, operation, attempt, error) from failure
            delay = READ_BACKOFF_SECONDS[attempt - 1]
            report["retries"].append(dict(host=host, operation=operation, attempt=attempt,
                                          next_attempt=attempt + 1, delay_seconds=delay,
                                          error=error))
            time.sleep(delay)


def git(*args: str, cwd: Path | None = None) -> str:
    try:
        result = subprocess.run(["git", *args], cwd=cwd, text=True, encoding="utf-8",
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    except subprocess.TimeoutExpired as failure:
        raise RuntimeError("Git command timed out after 120 seconds") from failure
    if result.returncode:
        # --porcelain puts rejection reasons (fetch first/non-fast-forward) on
        # stdout; stderr alone can contain only a generic atomic-push failure.
        raise RuntimeError(safe_error('\n'.join(part for part in
            (result.stderr.strip(), result.stdout.strip()) if part)))
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
              "updates": [], "conflicts": [], "errors": [], "retries": []}
    try:
        before = {host: remote_read(report, host, "inventory", lambda url=url: inventory(url))
                  for host, url in urls.items()}
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
                remote_read(report, host, "fetch", lambda host=host, url=url: git(
                    "fetch", "--quiet", "--no-tags", "--no-write-fetch-head", url,
                    f"+refs/heads/*:refs/sync/{host}/heads/*",
                    f"+refs/tags/*:refs/sync/{host}/tags/*", cwd=repo))
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
                        try:
                            git("push", "--atomic", "--porcelain", url,
                                *(f"{item['sha']}:{item['ref']}" for item in updates), cwd=repo)
                        except (RuntimeError, OSError) as failure:
                            # A timed-out push may have succeeded remotely. Do not
                            # blindly replay it; a later run starts from new refs.
                            raise RemoteOperationError(target, "push", 1, str(failure)) from failure
                after = {host: remote_read(report, host, "verify_refs", lambda url=url: inventory(url))
                         for host, url in urls.items()}
                report["refs_equal"] = after["github"] == after["gitverse"]
                if not report["refs_equal"] and not report["conflicts"]:
                    report["errors"].append("Remote refs changed during synchronization; retry.")
        report["status"] = ("conflict" if report["conflicts"] else
                            "failed" if report["errors"] else
                            "dry_run" if dry_run else "synchronized")
    except (RuntimeError, OSError) as failure:
        report["errors"].append(safe_error(str(failure)))
        if isinstance(failure, RemoteOperationError):
            report["failed_operation"] = failure.details
        report["status"] = "failed"
    return report


def reconcile(github: str, gitverse: str, *, dry_run: bool = False,
              work_dir: Path | None = None, attempts: int = 3) -> dict:
    """Recover from fresh refs, never blindly replay a planned push."""
    if not 1 <= attempts <= 3:
        raise ValueError('Reconciliation attempts must be between 1 and 3')
    rounds = []
    for number in range(1, attempts + 1):
        result = synchronize(github, gitverse, dry_run=dry_run, work_dir=work_dir)
        rounds.append(result)
        if result['status'] != 'failed' or dry_run:
            break
        failure = result.get('failed_operation')
        if failure:
            retryable = transient_read_failure(failure['host'], failure['error']) or (
                failure['operation'] == 'push' and any(marker in failure['error'].lower()
                    for marker in ('non-fast-forward', 'fetch first', 'stale info', 'cannot lock ref')))
        else:
            retryable = any('Remote refs changed' in error for error in result['errors'])
        if not retryable or number == attempts:
            break
        time.sleep((10, 30)[number - 1])
    # Retain failed/planned rounds even when new refs prove a lost push succeeded.
    return {**result, 'reconciliation_attempts': len(rounds), 'rounds': rounds}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--github", required=True)
    parser.add_argument("--gitverse", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument('--attempts', type=int, choices=range(1, 4), default=3)
    args = parser.parse_args()
    report = reconcile(args.github, args.gitverse, dry_run=args.dry_run,
                       work_dir=args.work_dir, attempts=args.attempts)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered + "\n", encoding="utf-8")
    return int(report["status"] in ("conflict", "failed"))


if __name__ == "__main__":
    raise SystemExit(main())

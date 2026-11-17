"""Real local bare repositories; no external services or credentials."""
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

spec = importlib.util.spec_from_file_location("git_host_sync", Path(__file__).parents[2] / "scripts/sync_git_hosts.py")
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


def command(repo, *args):
    result = subprocess.run(["git", "-C", str(repo), *args], check=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return result.stdout.strip()


@pytest.fixture
def hosts(tmp_path):
    work, gh, gv = (tmp_path / name for name in ("work", "github.git", "gitverse.git"))
    for target in (gh, gv):
        subprocess.run(["git", "init", "--bare", "--quiet", str(target)], check=True)
    subprocess.run(["git", "init", "--quiet", "-b", "dev", str(work)], check=True)
    command(work, "config", "user.name", "Sync test")
    command(work, "config", "user.email", "sync@example.test")
    command(work, "config", "commit.gpgsign", "false")
    command(work, "config", "core.hooksPath", str(tmp_path / "no-hooks"))
    (work / "content.txt").write_text("base", encoding="utf-8")
    command(work, "add", ".")
    command(work, "commit", "-qm", "base")
    for target in (gh, gv):
        command(work, "push", "--quiet", str(target), "HEAD:refs/heads/dev")
    return work, gh, gv


def commit(work, name, base="dev"):
    command(work, "switch", "--quiet", "-C", name, base)
    (work / "content.txt").write_text(name, encoding="utf-8")
    command(work, "add", ".")
    command(work, "commit", "-qm", name)
    return command(work, "rev-parse", "HEAD")


def test_no_changes(hosts):
    _, gh, gv = hosts
    report = sync.synchronize(str(gh), str(gv))
    assert report["status"] == "up_to_date"
    assert report["refs_equal"] is True


@pytest.mark.parametrize("source", ["github", "gitverse"])
def test_fast_forward_each_direction(hosts, source):
    work, gh, gv = hosts
    sha = commit(work, "advance")
    target = gh if source == "github" else gv
    command(work, "push", "--quiet", str(target), "HEAD:refs/heads/dev")
    report = sync.synchronize(str(gh), str(gv))
    assert report["status"] == "synchronized"
    assert report["updates"] == [dict(ref="refs/heads/dev", source=source,
        target="gitverse" if source == "github" else "github", sha=sha)]
    assert sync.inventory(str(gh)) == sync.inventory(str(gv))
    assert sync.synchronize(str(gh), str(gv))["status"] == "up_to_date"


def test_new_branches_and_annotated_and_lightweight_tags(hosts):
    work, gh, gv = hosts
    commit(work, "new")
    command(work, "tag", "--no-sign", "-a", "v1", "-m", "version one")
    command(work, "tag", "--no-sign", "v1-light")
    command(work, "push", "--quiet", str(gv), "HEAD:refs/heads/new", "refs/tags/v1", "refs/tags/v1-light")
    report = sync.synchronize(str(gh), str(gv))
    assert report["status"] == "synchronized"
    assert len(report["updates"]) == 3
    assert sync.inventory(str(gh)) == sync.inventory(str(gv))


def test_divergence_preserved_while_independent_branch_syncs(hosts):
    work, gh, gv = hosts
    gh_sha = commit(work, "gh-advance")
    command(work, "push", "--quiet", str(gh), "HEAD:refs/heads/dev")
    gv_sha = commit(work, "gv-advance")
    command(work, "push", "--quiet", str(gv), "HEAD:refs/heads/dev", "HEAD:refs/heads/new")
    report = sync.synchronize(str(gh), str(gv))
    assert report["status"] == "conflict"
    assert report["conflicts"][0]["reason"] == "divergent_history"
    assert sync.inventory(str(gh))["refs/heads/dev"] == gh_sha
    assert sync.inventory(str(gv))["refs/heads/dev"] == gv_sha
    assert sync.inventory(str(gh))["refs/heads/new"] == gv_sha


def test_existing_tags_are_immutable(hosts):
    work, gh, gv = hosts
    command(work, "push", "--quiet", str(gh), "HEAD:refs/tags/v1")
    commit(work, "advance")
    command(work, "push", "--quiet", str(gv), "HEAD:refs/tags/v1")
    gh_before, gv_before = sync.inventory(str(gh)), sync.inventory(str(gv))
    report = sync.synchronize(str(gh), str(gv))
    assert report["status"] == "conflict"
    assert report["conflicts"][0]["reason"] == "different_tag"
    assert sync.inventory(str(gh)) == gh_before
    assert sync.inventory(str(gv)) == gv_before


def test_dry_run_does_not_push(hosts):
    work, gh, gv = hosts
    commit(work, "advance")
    command(work, "push", "--quiet", str(gv), "HEAD:refs/heads/dev")
    before = sync.inventory(str(gh))
    report = sync.synchronize(str(gh), str(gv), dry_run=True)
    assert report["status"] == "dry_run"
    assert len(report["updates"]) == 1
    assert sync.inventory(str(gh)) == before


def test_missing_branch_restored_without_deletion(hosts):
    work, gh, gv = hosts
    command(work, "push", "--quiet", str(gv), ":refs/heads/dev")
    report = sync.synchronize(str(gh), str(gv))
    assert report["status"] == "synchronized"
    assert sync.inventory(str(gh)) == sync.inventory(str(gv))


def test_concurrent_divergence_rejected_by_non_force_push(hosts, monkeypatch):
    work, gh, gv = hosts
    gv_sha = commit(work, "gv-new")
    command(work, "push", "--quiet", str(gv), "HEAD:refs/heads/dev")
    original = sync.git
    concurrent = []
    def race(*args, **kwargs):
        if args[:3] == ("push", "--atomic", "--porcelain") and args[3] == str(gh):
            concurrent.append(commit(work, "concurrent"))
            command(work, "push", "--quiet", str(gh), "HEAD:refs/heads/dev")
        return original(*args, **kwargs)
    monkeypatch.setattr(sync, "git", race)
    report = sync.synchronize(str(gh), str(gv))
    assert report["status"] == "failed"
    assert sync.inventory(str(gh))["refs/heads/dev"] == concurrent[0]
    assert sync.inventory(str(gv))["refs/heads/dev"] == gv_sha


RPC_403 = "error: RPC failed; HTTP 403 curl 22 The requested URL returned error: 403\nfatal: expected flush after ref listing"


@pytest.mark.parametrize("operation", ["inventory", "fetch", "verify_refs"])
def test_transient_gitverse_read_recovers_without_replaying_push(hosts, monkeypatch, operation):
    work, gh, gv = hosts
    commit(work, "gitverse-ahead")
    command(work, "push", "--quiet", str(gv), "HEAD:refs/heads/dev")
    original = sync.git
    failed = []
    reads = []
    pushes = []
    sleeps = []

    def flaky(*args, **kwargs):
        is_inventory = args[0] == "ls-remote" and args[-1] == str(gv)
        if is_inventory:
            reads.append(args)
        if args[0] == "push":
            pushes.append(args)
        matches = (operation == "inventory" and is_inventory and len(reads) == 1
                   or operation == "verify_refs" and is_inventory and len(reads) == 2
                   or operation == "fetch" and args[0] == "fetch" and str(gv) in args)
        if matches and not failed:
            failed.append(True)
            raise RuntimeError(RPC_403)
        return original(*args, **kwargs)

    monkeypatch.setattr(sync, "git", flaky)
    monkeypatch.setattr(sync.time, "sleep", sleeps.append)
    report = sync.synchronize(str(gh), str(gv))
    assert report["status"] == "synchronized", report
    assert report["refs_equal"] is True
    assert len(pushes) == 1
    assert sleeps == [2]
    assert report["retries"] == [dict(host="gitverse", operation=operation,
        attempt=1, next_attempt=2, delay_seconds=2, error=RPC_403)]
    assert sync.inventory(str(gh)) == sync.inventory(str(gv))


def test_repeated_gitverse_rpc_403_fails_with_bounded_attempts_and_context(hosts, monkeypatch):
    _, gh, gv = hosts
    original = sync.git
    failed = []
    sleeps = []

    def unavailable(*args, **kwargs):
        if args[0] == "ls-remote" and args[-1] == str(gv):
            failed.append(True)
            raise RuntimeError(RPC_403)
        assert args[0] != "push", "No writes may occur after failed inventory"
        return original(*args, **kwargs)

    monkeypatch.setattr(sync, "git", unavailable)
    monkeypatch.setattr(sync.time, "sleep", sleeps.append)
    report = sync.synchronize(str(gh), str(gv))
    assert report["status"] == "failed"
    assert len(failed) == 3
    assert sleeps == [2, 5]
    assert report["updates"] == []
    assert report["failed_operation"] == dict(host="gitverse", operation="inventory",
        attempts=3, error=RPC_403)
    assert "gitverse/inventory failed after 3" in report["errors"][0]


@pytest.mark.parametrize("error", [
    "fatal: Authentication failed for 'https://user:private-token@gitverse.ru/project'",
    "fatal: unable to access 'https://gitverse.ru/project': The requested URL returned error: 403",
    "Permission denied (publickey).",
    "fatal: SSL certificate problem: certificate has expired",
    "fatal: repository not found",
])
def test_permanent_auth_and_security_errors_fail_without_retry_or_secret_leak(hosts, monkeypatch, error):
    _, gh, gv = hosts
    original = sync.git
    calls = []

    def denied(*args, **kwargs):
        if args[0] == "ls-remote" and args[-1] == str(gv):
            calls.append(True)
            raise RuntimeError(error)
        return original(*args, **kwargs)

    monkeypatch.setattr(sync, "git", denied)
    monkeypatch.setattr(sync.time, "sleep", lambda _: pytest.fail("Permanent failures must not retry"))
    report = sync.synchronize(str(gh), str(gv))
    assert report["status"] == "failed"
    assert len(calls) == 1
    assert report["retries"] == []
    assert report["failed_operation"]["attempts"] == 1
    assert "private-token" not in json.dumps(report)


def test_gitverse_rpc_exception_does_not_retry_arbitrary_github_403(hosts, monkeypatch):
    _, gh, gv = hosts
    original = sync.git

    def denied(*args, **kwargs):
        if args[0] == "ls-remote" and args[-1] == str(gh):
            raise RuntimeError(RPC_403)
        return original(*args, **kwargs)

    monkeypatch.setattr(sync, "git", denied)
    monkeypatch.setattr(sync.time, "sleep", lambda _: pytest.fail("Unclassified 403 must not retry"))
    report = sync.synchronize(str(gh), str(gv))
    assert report["status"] == "failed"
    assert report["failed_operation"]["host"] == "github"
    assert report["failed_operation"]["attempts"] == 1


@pytest.mark.parametrize("error", ["HTTP 502 Bad Gateway", "Could not resolve host: github.com", "Git command timed out after 120 seconds"])
def test_temporary_transport_failure_recovers_on_github_read(hosts, monkeypatch, error):
    _, gh, gv = hosts
    original = sync.git
    failed = []
    sleeps = []

    def flaky(*args, **kwargs):
        if args[0] == "ls-remote" and args[-1] == str(gh) and not failed:
            failed.append(True)
            raise RuntimeError(error)
        return original(*args, **kwargs)

    monkeypatch.setattr(sync, "git", flaky)
    monkeypatch.setattr(sync.time, "sleep", sleeps.append)
    report = sync.synchronize(str(gh), str(gv))
    assert report["status"] == "up_to_date"
    assert report["refs_equal"] is True
    assert sleeps == [2]
    assert report["retries"][0]["host"] == "github"


def test_push_with_lost_response_is_not_replayed_and_next_run_reconciles(hosts, monkeypatch):
    work, gh, gv = hosts
    commit(work, "github-ahead")
    command(work, "push", "--quiet", str(gh), "HEAD:refs/heads/dev")
    original = sync.git
    pushes = []

    def lost_response(*args, **kwargs):
        if args[0] == "push":
            pushes.append(args)
            original(*args, **kwargs)
            raise RuntimeError("Git command timed out after 120 seconds")
        return original(*args, **kwargs)

    monkeypatch.setattr(sync, "git", lost_response)
    monkeypatch.setattr(sync.time, "sleep", lambda _: pytest.fail("A push must never be replayed blindly"))
    report = sync.synchronize(str(gh), str(gv))
    assert report["status"] == "failed"
    assert report["failed_operation"] == dict(host="gitverse", operation="push", attempts=1,
                                             error="Git command timed out after 120 seconds")
    assert len(pushes) == 1
    assert sync.inventory(str(gh)) == sync.inventory(str(gv))
    assert sync.synchronize(str(gh), str(gv))["status"] == "up_to_date"
    assert len(pushes) == 1


def test_git_command_has_a_timeout(monkeypatch):
    def timeout(*args, **kwargs):
        assert kwargs["timeout"] == 120
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])
    monkeypatch.setattr(sync.subprocess, "run", timeout)
    with pytest.raises(RuntimeError, match="Git command timed out after 120 seconds"):
        sync.git("ls-remote", "https://example.test/repo")


def test_reconcile_lost_push_response_checks_refs_without_second_push(hosts, monkeypatch):
    work, gh, gv = hosts
    commit(work, 'github-ahead')
    command(work, 'push', '--quiet', str(gh), 'HEAD:refs/heads/dev')
    original = sync.git
    pushes = []
    def lost_response(*args, **kwargs):
        result = original(*args, **kwargs)
        if args[0] == 'push':
            pushes.append(args)
            raise RuntimeError('Git command timed out after 120 seconds')
        return result
    monkeypatch.setattr(sync, 'git', lost_response)
    monkeypatch.setattr(sync.time, 'sleep', lambda _: None)
    report = sync.reconcile(str(gh), str(gv))
    assert report['status'] == 'up_to_date' and report['refs_equal']
    assert report['reconciliation_attempts'] == 2 and len(pushes) == 1
    assert report['rounds'][0]['failed_operation']['operation'] == 'push'


def test_reconcile_recovers_push_transport_failure_from_new_plan(hosts, monkeypatch):
    work, gh, gv = hosts
    commit(work, 'gitverse-ahead')
    command(work, 'push', '--quiet', str(gv), 'HEAD:refs/heads/dev')
    original = sync.git
    pushes = []
    def disconnected(*args, **kwargs):
        if args[0] == 'push':
            pushes.append(args)
            if len(pushes) == 1:
                raise RuntimeError('Connection reset by peer')
        return original(*args, **kwargs)
    monkeypatch.setattr(sync, 'git', disconnected)
    monkeypatch.setattr(sync.time, 'sleep', lambda _: None)
    report = sync.reconcile(str(gh), str(gv))
    assert report['status'] == 'synchronized' and report['refs_equal']
    assert report['reconciliation_attempts'] == 2
    assert sync.inventory(str(gh)) == sync.inventory(str(gv))


def test_reconcile_change_during_verification_is_picked_up(hosts, monkeypatch):
    work, gh, gv = hosts
    commit(work, 'first')
    command(work, 'push', '--quiet', str(gh), 'HEAD:refs/heads/dev')
    original = sync.inventory
    gh_reads = []
    def changed(url):
        if url == str(gh):
            gh_reads.append(url)
            if len(gh_reads) == 2:
                commit(work, 'second', base='first')
                command(work, 'push', '--quiet', str(gh), 'HEAD:refs/heads/dev')
        return original(url)
    monkeypatch.setattr(sync, 'inventory', changed)
    monkeypatch.setattr(sync.time, 'sleep', lambda _: None)
    report = sync.reconcile(str(gh), str(gv))
    assert report['status'] == 'synchronized' and report['refs_equal']
    assert report['reconciliation_attempts'] == 2
    assert sync.inventory(str(gv))['refs/heads/dev'] == command(work, 'rev-parse', 'second')


def test_reconcile_concurrent_writer_is_not_overwritten(hosts, monkeypatch):
    work, gh, gv = hosts
    first = commit(work, 'github-ahead')
    command(work, 'push', '--quiet', str(gh), 'HEAD:refs/heads/dev')
    original = sync.git
    races = []
    def raced(*args, **kwargs):
        if args[0] == 'push' and not races:
            races.append(commit(work, 'concurrent-gitverse'))
            command(work, 'push', '--quiet', str(gv), 'HEAD:refs/heads/dev')
        return original(*args, **kwargs)
    monkeypatch.setattr(sync, 'git', raced)
    monkeypatch.setattr(sync.time, 'sleep', lambda _: None)
    report = sync.reconcile(str(gh), str(gv))
    assert report['status'] == 'conflict', report['errors']
    assert report['reconciliation_attempts'] == 2
    assert sync.inventory(str(gh))['refs/heads/dev'] == first
    assert sync.inventory(str(gv))['refs/heads/dev'] == races[0]


def test_reconcile_partial_two_host_delivery_recovers_without_duplicate_push(hosts, monkeypatch):
    work, gh, gv = hosts
    commit(work, 'gh-only')
    command(work, 'push', '--quiet', str(gh), 'HEAD:refs/heads/from-gh')
    commit(work, 'gv-only')
    command(work, 'push', '--quiet', str(gv), 'HEAD:refs/heads/from-gv')
    original = sync.git
    pushes = []
    def interrupted(*args, **kwargs):
        if args[0] == 'push':
            pushes.append(args[3])
            if len(pushes) == 2:
                raise RuntimeError('Connection reset by peer')
        return original(*args, **kwargs)
    monkeypatch.setattr(sync, 'git', interrupted)
    monkeypatch.setattr(sync.time, 'sleep', lambda _: None)
    report = sync.reconcile(str(gh), str(gv))
    assert report['refs_equal'] and report['reconciliation_attempts'] == 2
    assert pushes == [str(gh), str(gv), str(gv)]
    assert sync.inventory(str(gh)) == sync.inventory(str(gv))


def test_reconcile_permanent_auth_failure_is_not_retried(hosts, monkeypatch):
    _, gh, gv = hosts
    original = sync.git
    def denied(*args, **kwargs):
        if args[0] == 'ls-remote' and args[-1] == str(gv):
            raise RuntimeError('Authentication failed')
        return original(*args, **kwargs)
    monkeypatch.setattr(sync, 'git', denied)
    monkeypatch.setattr(sync.time, 'sleep', lambda _: pytest.fail('Permanent auth failure must stop'))
    report = sync.reconcile(str(gh), str(gv))
    assert report['status'] == 'failed' and report['reconciliation_attempts'] == 1


def test_reconcile_transport_outage_is_bounded(hosts, monkeypatch):
    _, gh, gv = hosts
    original = sync.git
    failures = []
    def unavailable(*args, **kwargs):
        if args[0] == 'ls-remote' and args[-1] == str(gv):
            failures.append(args)
            raise RuntimeError(RPC_403)
        return original(*args, **kwargs)
    monkeypatch.setattr(sync, 'git', unavailable)
    monkeypatch.setattr(sync.time, 'sleep', lambda _: None)
    report = sync.reconcile(str(gh), str(gv))
    assert report['status'] == 'failed' and report['reconciliation_attempts'] == 3
    assert len(failures) == 9 and len(report['rounds']) == 3

"""Real local bare repositories; no external services or credentials."""
import importlib.util
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

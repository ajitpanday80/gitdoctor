from gitdoctor.branches import check_branches, check_state

from helpers import commit, make_repo, sh

OLD = "2020-01-01T00:00:00"


def titles(findings):
    return {f.title for f in findings}


def test_merged_and_unmerged_stale_branches(tmp_path):
    repo = make_repo(tmp_path / "r")
    commit(repo, {"a": "1"}, date=OLD)
    sh(repo, "checkout", "-q", "-b", "done")
    commit(repo, {"b": "1"}, date=OLD)
    sh(repo, "checkout", "-q", "main")
    sh(repo, "merge", "-q", "--no-ff", "done", "-m", "merge", date=OLD)
    sh(repo, "checkout", "-q", "-b", "wip")
    commit(repo, {"c": "1"}, date=OLD)
    sh(repo, "checkout", "-q", "main")
    got = {f.title: f for f in check_branches(repo, stale_days=90)}
    assert "done" in got["Merged branch, safe to delete"].detail
    assert got["Merged branch, safe to delete"].fix == "git branch -d done"
    assert "wip" in got["Stale unmerged branch"].detail
    assert "1 commit(s)" in got["Stale unmerged branch"].detail


def test_fresh_branches_are_ignored(tmp_path):
    repo = make_repo(tmp_path / "r")
    commit(repo, {"a": "1"})
    sh(repo, "branch", "feature")
    assert check_branches(repo, stale_days=90) == []


def test_dirty_state(tmp_path):
    repo = make_repo(tmp_path / "r")
    commit(repo, {"a": "1"})
    (repo / "new.txt").write_text("x")
    assert "Uncommitted changes" in titles(check_state(repo))


def test_unpushed_commits(tmp_path):
    origin = make_repo(tmp_path / "origin")
    commit(origin, {"a": "1"})
    clone = tmp_path / "clone"
    sh(tmp_path, "clone", "-q", str(origin), str(clone))
    commit(clone, {"b": "1"})
    assert "Unpushed commits" in titles(check_state(clone))


def test_empty_repo_is_fine(tmp_path):
    repo = make_repo(tmp_path / "r")
    assert check_branches(repo) == [] and check_state(repo) == []

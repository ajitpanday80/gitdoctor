import json

from gitdoctor.cli import main
from gitdoctor.discover import find_repos

from helpers import aws_key, commit, make_repo


def test_discovery_does_not_descend_into_repos(tmp_path):
    a = make_repo(tmp_path / "a")
    make_repo(a / "nested")
    make_repo(tmp_path / "deep" / "b")
    (tmp_path / "node_modules" / "x").mkdir(parents=True)
    make_repo(tmp_path / "node_modules" / "x" / "ignored")
    names = sorted(p.name for p in find_repos([tmp_path]))
    assert names == ["a", "b"]


def test_exit_code_and_json(tmp_path, capsys):
    repo = make_repo(tmp_path / "leaky")
    commit(repo, {"x.env": f"K={aws_key()}\n"})
    clean = make_repo(tmp_path / "clean")
    commit(clean, {"a": "1"})

    code = main([str(tmp_path), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert code == 1
    by_name = {r["name"]: r for r in data["repos"]}
    assert by_name["clean"]["score"] == 100 and by_name["clean"]["grade"] == "A"
    assert by_name["leaky"]["score"] < 100
    assert aws_key() not in json.dumps(data)  # secrets are never emitted in full

    assert main([str(tmp_path), "--json", "--fail-on", "never"]) == 0
    capsys.readouterr()


def test_no_repos_exits_2(tmp_path, capsys):
    assert main([str(tmp_path)]) == 2


def test_text_report_renders(tmp_path, capsys):
    repo = make_repo(tmp_path / "r")
    commit(repo, {"x.env": f"K={aws_key()}\n"})
    main([str(tmp_path), "--color", "never"])
    out = capsys.readouterr().out
    assert "AWS access key ID" in out and "x.env:1" in out and aws_key() not in out


def test_dogfood_repo_is_clean():
    # gitdoctor must never ship its own secrets.
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    assert main([str(root), "--color", "never", "--fail-on", "medium"]) == 0


def test_high_severity_secret_caps_score(tmp_path, capsys):
    repo = make_repo(tmp_path / "leaky")
    commit(repo, {"x.env": f"K={aws_key()}\n"})
    main([str(tmp_path), "--json", "--fail-on", "never"])
    repo_report = json.loads(capsys.readouterr().out)["repos"][0]
    assert repo_report["score"] <= 55 and repo_report["grade"] in ("D", "F")


def test_gitdoctorignore_file(tmp_path, capsys):
    repo = make_repo(tmp_path / "r")
    commit(repo, {"fixtures/a.env": f"K={aws_key()}\n", ".gitdoctorignore": "# fake data\nfixtures/\n"})
    assert main([str(tmp_path), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["repos"][0]["findings"] == []


def test_staged_mode_blocks_commit_and_ignores_history(tmp_path, capsys, monkeypatch):
    from helpers import sh

    repo = make_repo(tmp_path / "r")
    commit(repo, {"old.env": f"K={aws_key()}\n"})  # already committed: staged mode must not care
    (repo / "new.env").write_text(f"K={aws_key()[:-1]}Z\n")
    sh(repo, "add", "new.env")
    monkeypatch.chdir(repo / ".")
    assert main(["--staged", "--color", "never"]) == 1
    assert "new.env:1" in capsys.readouterr().out
    sh(repo, "reset", "-q")
    assert main(["--staged", "--color", "never"]) == 0


def test_sarif_output(tmp_path, capsys):
    repo = make_repo(tmp_path / "r")
    commit(repo, {"cfg/x.env": f"K={aws_key()}\n"})
    main([str(tmp_path), "--format", "sarif", "--fail-on", "never"])
    out = capsys.readouterr().out
    doc = json.loads(out)
    res = doc["runs"][0]["results"][0]
    assert doc["version"] == "2.1.0" and res["ruleId"] == "aws-access-key" and res["level"] == "error"
    loc = res["locations"][0]["physicalLocation"]
    assert loc["artifactLocation"]["uri"] == "cfg/x.env" and loc["region"]["startLine"] == 1
    assert aws_key() not in out


def test_prune_merged_deletes_only_merged(tmp_path, capsys):
    from helpers import sh

    old = "2020-01-01T00:00:00"
    repo = make_repo(tmp_path / "r")
    commit(repo, {"a": "1"}, date=old)
    sh(repo, "checkout", "-q", "-b", "done")
    commit(repo, {"b": "1"}, date=old)
    sh(repo, "checkout", "-q", "main")
    sh(repo, "merge", "-q", "--no-ff", "done", "-m", "m", date=old)
    sh(repo, "checkout", "-q", "-b", "wip")
    commit(repo, {"c": "1"}, date=old)
    sh(repo, "checkout", "-q", "main")
    main([str(tmp_path), "--prune-merged", "--yes", "--color", "never", "--fail-on", "never"])
    branches = sh(repo, "branch", "--format=%(refname:short)").split()
    assert "done" not in branches and "wip" in branches and "main" in branches

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

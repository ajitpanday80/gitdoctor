from gitdoctor.secrets import entropy, scan_line, scan_history, scan_working_tree

from helpers import aws_key, commit, github_token, make_repo, sh


def rules(line):
    return [h.rule.id for h in scan_line(line)]


def test_detects_provider_tokens():
    assert rules(f"key = {aws_key()}") == ["aws-access-key"]
    assert rules(f"export T={github_token()}") == ["github-token"]


def test_detects_private_key_header():
    assert rules("-----BEGIN RSA PRIVATE KEY-----") == ["private-key"]  # gitdoctor:ignore


def test_generic_needs_entropy_and_not_placeholder():
    assert rules('api_key = "x9Qv2LmPz7Rt4WnB"') == ["generic-secret"]  # gitdoctor:ignore
    assert rules('api_key = "your_api_key_here"') == []
    assert rules('password = "aaaaaaaaaa"') == []  # low entropy
    assert rules('token = "${TOKEN_FROM_ENV}"') == []


def test_inline_ignore_marker():
    assert rules(f"key = {aws_key()}  # gitdoctor:ignore") == []


def test_entropy_ordering():
    assert entropy("aaaa") < entropy("a1B2c3D4")


def test_working_tree_and_redaction(tmp_path):
    repo = make_repo(tmp_path / "r")
    commit(repo, {"cfg/prod.env": f"AWS={aws_key()}\n", "README.md": "hi\n"})
    found = scan_working_tree(repo)
    assert len(found) == 1
    f = found[0]
    assert (f.path, f.line) == ("cfg/prod.env", 1)
    assert aws_key() not in f.detail  # never print the full secret
    assert f.detail.startswith(aws_key()[:4])


def test_excludes_and_binary_skip(tmp_path):
    repo = make_repo(tmp_path / "r")
    commit(repo, {"fixtures/a.txt": aws_key() + "\n", "pic.png": aws_key()})
    assert scan_working_tree(repo, excludes=["fixtures/*"]) == []


def test_history_finds_removed_secret(tmp_path):
    repo = make_repo(tmp_path / "r")
    commit(repo, {"a.env": f"K={aws_key()}\n"}, "add secret")
    commit(repo, {"a.env": "K=removed\n"}, "remove secret")
    assert scan_working_tree(repo) == []
    hist = scan_history(repo)
    assert len(hist) == 1 and hist[0].commit and "history only" in hist[0].detail


def test_history_skips_known_fingerprints(tmp_path):
    repo = make_repo(tmp_path / "r")
    commit(repo, {"a.env": f"K={aws_key()}\n"})
    tree = scan_working_tree(repo)
    assert scan_history(repo, skip=[f.fingerprint for f in tree]) == []


def test_new_provider_rules():
    gitlab = "gl" + "pat-" + "abcdefghij1234567890"
    npm = "np" + "m_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"
    anthropic = "sk-" + "ant-" + "api03-abcdefghijklmnopqrstuv"
    hook = "https://hooks." + "slack.com/services/T0ABC123/B0DEF456/abcdEFGH1234ijklMNOP"
    assert rules(f"x={gitlab}") == ["gitlab-token"]
    assert rules(f"x={npm}") == ["npm-token"]
    assert rules(f"x={anthropic}") == ["anthropic-key"]
    assert rules(f"x={hook}") == ["slack-webhook"]


def test_db_url_needs_a_real_password():
    url = "postgres" + "://app:s3cr3tpw@db.internal:5432/prod"
    assert rules(f"DATABASE_URL={url}") == ["db-url-password"]
    assert rules("DATABASE_URL=postgres://app:${DB_PASSWORD}@db/prod") == []
    assert rules("DATABASE_URL=postgres://localhost:5432/prod") == []


def test_staged_scan_only_sees_staged_lines(tmp_path):
    from gitdoctor.secrets import scan_staged

    repo = make_repo(tmp_path / "r")
    commit(repo, {"a.txt": "hello\n"})
    (repo / "leak.env").write_text(f"K={aws_key()}\n")
    (repo / "unstaged.env").write_text(f"K={github_token()}\n")
    sh(repo, "add", "leak.env")
    found = scan_staged(repo)
    assert [(f.path, f.line) for f in found] == [("leak.env", 1)]
    assert "staged" in found[0].detail and aws_key() not in found[0].detail

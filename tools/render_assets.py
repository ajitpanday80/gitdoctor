#!/usr/bin/env python3
"""Render README images from REAL gitdoctor output (no mock-ups).

Needs: playwright (+ chromium), ffmpeg, Pillow.
    python tools/render_assets.py
"""
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

PALETTE = {  # xterm-256 colours used by gitdoctor
    "38;5;203": "#ff6b6b", "38;5;221": "#ffd479", "38;5;114": "#8ce99a",
    "38;5;111": "#74b9ff", "38;5;183": "#d0a9ff", "38;5;245": "#7d8590",
}
ANSI = re.compile(r"\x1b\[([0-9;]*)m")


def ansi_to_html(text: str) -> str:
    out, stack = [], []
    pos = 0
    for m in ANSI.finditer(text):
        out.append(html.escape(text[pos:m.start()]))
        code = m.group(1)
        if code in ("0", ""):
            out.append("</span>" * len(stack)); stack = []
        elif code == "1":
            out.append('<span style="font-weight:700">'); stack.append(code)
        elif code == "2":
            out.append('<span style="opacity:.55">'); stack.append(code)
        elif code in PALETTE:
            out.append(f'<span style="color:{PALETTE[code]}">'); stack.append(code)
        pos = m.end()
    out.append(html.escape(text[pos:]))
    out.append("</span>" * len(stack))
    return "".join(out)


PAGE = """<!doctype html><meta charset=utf-8><style>
html,body{{margin:0;background:transparent}}
.win{{display:inline-block;margin:28px;background:#0d1117;border-radius:12px;
 box-shadow:0 20px 60px rgba(0,0,0,.55),0 0 0 1px #30363d;overflow:hidden;min-width:{minw}px}}
.bar{{height:38px;background:#161b22;display:flex;align-items:center;padding:0 14px;gap:8px;border-bottom:1px solid #30363d}}
.dot{{width:12px;height:12px;border-radius:50%}}
.title{{margin:0 auto;color:#7d8590;font:13px -apple-system,Segoe UI,Helvetica,sans-serif;transform:translateX(-24px)}}
pre{{margin:0;padding:18px 22px 22px;color:#e6edf3;font:14.5px/1.45 'DejaVu Sans Mono','Menlo','Consolas',monospace;white-space:pre}}
.cur{{display:inline-block;width:9px;height:17px;background:#e6edf3;vertical-align:-3px}}
</style><div class=win id=w><div class=bar><i class=dot style=background:#ff5f56></i><i class=dot style=background:#ffbd2e></i><i class=dot style=background:#27c93f></i><span class=title>{title}</span></div><pre>{body}</pre></div>"""


def page(body_html: str, title: str, minw: int = 0) -> str:
    return PAGE.format(body=body_html, title=title, minw=minw)


def main():
    from playwright.sync_api import sync_playwright

    work = Path(tempfile.mkdtemp(prefix="gd-assets-"))
    home = work / "home"; code = home / "code"; code.mkdir(parents=True)
    subprocess.run([sys.executable, str(ROOT / "tools" / "make_demo.py"), str(code)], check=True)
    env = {**os.environ, "HOME": str(home), "TERM": "xterm-256color"}

    def run(*args):
        r = subprocess.run(["gitdoctor", *args, "--color", "always"], capture_output=True, text=True, env=env, cwd=home)
        return r.stdout.rstrip("\n")

    shots = {
        "screenshot.png": ("gitdoctor ~/code", "$ gitdoctor ~/code\n" + run(str(code))),
        "history.png": ("gitdoctor ~/code --history", "$ gitdoctor ~/code --history\n" + run(str(code), "--history")),
    }
    # a real pre-commit hook blocking a real commit
    hook_repo = code / "payments-api"
    hook = hook_repo / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\ngitdoctor --staged --color always\n"); hook.chmod(0o755)
    key = "AK" + "IA" + "7XQ2MZPL4TWB9KDC"
    (hook_repo / "config" / "staging.env").write_text(f"AWS_ACCESS_KEY_ID={key}\nAWS_REGION=eu-west-1\n")
    genv = {**env, "GIT_AUTHOR_NAME": "Dev", "GIT_AUTHOR_EMAIL": "d@e.co", "GIT_COMMITTER_NAME": "Dev", "GIT_COMMITTER_EMAIL": "d@e.co"}
    subprocess.run(["git", "-C", str(hook_repo), "add", "config/staging.env"], check=True, env=genv)
    r = subprocess.run(["git", "-C", str(hook_repo), "commit", "-m", "add staging config"], capture_output=True, text=True, env=genv)
    assert r.returncode != 0, "hook should have blocked the commit"
    blocked = (r.stdout + r.stderr).rstrip("\n")
    shots["hook.png"] = ("git commit", "$ git commit -m \"add staging config\"\n" + blocked)
    # the typed command should look like a prompt, not an escape-coded string
    prompt = lambda s: re.sub(r"^\$ (.*)\n", lambda m: f"\x1b[38;5;114m❯\x1b[0m \x1b[1m{m.group(1)}\x1b[0m\n", s, count=1)

    DOCS.mkdir(exist_ok=True)
    with sync_playwright() as pw:
        exe = os.environ.get("CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        ctx = browser.new_context(device_scale_factor=2, viewport={"width": 1100, "height": 900})
        pg = ctx.new_page()
        for name, (title, text) in shots.items():
            pg.set_content(page(ansi_to_html(prompt(text)), title, 860))
            pg.locator("#w").screenshot(path=str(DOCS / name), omit_background=True)

        # ---- animated demo: type the command, then reveal output in chunks
        history_text = prompt(shots["history.png"][1])
        head, _, rest = history_text.partition("\n")
        cmd = "gitdoctor ~/code --history"
        lines = rest.split("\n")
        frames = []  # (text_with_cursor, duration_ms)
        prompt_pre = "\x1b[38;5;114m❯\x1b[0m "
        frames.append((prompt_pre, 700))
        for i in range(1, len(cmd) + 1):
            frames.append((prompt_pre + "\x1b[1m" + cmd[:i] + "\x1b[0m", 55))
        frames.append((head, 450))
        step = 5
        for n in range(step, len(lines) + step, step):
            frames.append((head + "\n" + "\n".join(lines[:n]), 140))
        frames.append((head + "\n" + "\n".join(lines), 3500))

        # GIF: fixed-height terminal that scrolls, rendered at 1x to keep the file small
        gctx = browser.new_context(device_scale_factor=1, viewport={"width": 1000, "height": 800})
        gp = gctx.new_page()
        fdir = work / "frames"; fdir.mkdir()
        rows = 31
        for i, (txt, _) in enumerate(frames):
            vis = txt.split("\n")[-rows:]
            vis += [""] * (rows - len(vis))
            body = ansi_to_html("\n".join(vis))
            if i < len(frames) - 1:
                # cursor sits at the end of the last non-empty line
                body = body.rstrip("\n") + '<span class=cur></span>' if txt.count("\n") < rows - 1 else body
            gp.set_content(page(body, "gitdoctor", 860).replace("<pre>", f"<pre style='height:{rows * 21.03:.0f}px;box-sizing:content-box'>"))
            gp.locator("#w").screenshot(path=str(fdir / f"f{i:04d}.png"))
        browser.close()

    from PIL import Image
    imgs, durs = [], [d for _, d in frames]
    for p in sorted(fdir.glob("f*.png")):
        imgs.append(Image.open(p).convert("RGB"))
    imgs[0].save(DOCS / "demo.gif", save_all=True, append_images=imgs[1:], duration=durs, loop=0,
                 optimize=True, disposal=2)
    shutil.rmtree(work, ignore_errors=True)
    print("wrote", [p.name for p in DOCS.iterdir()])


if __name__ == "__main__":
    main()

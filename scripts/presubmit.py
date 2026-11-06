#!/usr/bin/env python3
"""Check the repository against the contest's submission rules before you submit.

    ./siege presubmit

Rules checked (from the official rules): a public repository with an
open-source licence visible on its page; evidence that the project genuinely
builds for or runs on QNX 8.0, with the version, target and toolchain stated;
build and run instructions; no third-party binaries; the Codelab reachable if
you are entering the bonus. Items that only a person can do (the video, the
form) are listed at the end. Exit code 1 if any check fails.
"""
import datetime, json, os, re, subprocess, sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
G, R, Y, D, B, X = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[1m", "\033[0m"
failures = 0


def sh(cmd, timeout=60):
    try:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)


def check(ok, what, detail="", fix="", warn=False):
    global failures
    mark = f"{G}ok{X}" if ok else (f"{Y}!!{X}" if warn else f"{R}no{X}")
    print(f"  [{mark}] {what}" + (f"  {D}{detail}{X}" if detail else ""))
    if not ok:
        if not warn:
            failures += 1
        if fix:
            print(f"        fix: {fix}")


def read(path):
    try:
        with open(os.path.join(ROOT, path), errors="replace") as f:
            return f.read()
    except OSError:
        return ""


print(f"{B}siege presubmit{X}")

# ---- the repository on GitHub -------------------------------------------------------------
code, url = sh(["git", "remote", "get-url", "origin"])
m = re.search(r"github\.com[:/]([^/]+)/([^/.]+)", url) if code == 0 else None
slug = f"{m.group(1)}/{m.group(2)}" if m else None
print(f"\n{B}Repository{X}")
check(bool(slug), "a GitHub remote is configured", slug or "", "git remote add origin https://github.com/<you>/siege-qnx.git")
if slug:
    code, out = sh(["gh", "repo", "view", slug, "--json", "visibility,licenseInfo,url"])
    if code == 0:
        info = json.loads(out)
        check(info["visibility"] == "PUBLIC", "the repository is public", info["visibility"],
              f"gh repo edit {slug} --visibility public --accept-visibility-change-consequences")
        lic = (info.get("licenseInfo") or {}).get("name")
        check(bool(lic), "an open-source licence is detected on the repository page", lic or "none",
              "add a LICENSE file at the top level and push it")
    else:
        check(False, "could read the repository from GitHub", out[:100], "install and log in to the GitHub CLI: gh auth login", warn=True)
code, out = sh(["git", "status", "-sb"])
first = out.splitlines()[0] if out else ""
check("ahead" not in first and "behind" not in first, "everything is pushed", first, "git push")
code, out = sh(["git", "status", "--porcelain", "--untracked-files=no"])
check(not out, "no uncommitted changes to tracked files", out[:80])
check(os.path.exists(os.path.join(ROOT, "LICENSE")), "LICENSE is at the top level of the repository")

# ---- evidence that it runs on QNX 8.0 -------------------------------------------------------
print(f"\n{B}QNX evidence and instructions{X}")
readme = read("README.md")
for what, pat in (("QNX version (SDP 8.0) stated", r"QNX SDP 8\.0"), ("target stated (aarch64le on QEMU)", r"aarch64le.*QEMU|QEMU.*aarch64le"),
                  ("toolchain stated (qcc)", r"qcc -Vgcc_ntoaarch64le"), ("build and run instructions", r"## Build and run"),
                  ("a section pointing reviewers at the QNX-specific code", r"## Where QNX is used")):
    check(bool(re.search(pat, readme, re.S)), what)
api = sum(read(f"pipeline/{f}").count("MsgSend") for f in os.listdir(os.path.join(ROOT, "pipeline")) if f.endswith(".c"))
check(api > 0, "QNX-specific source is present (native message passing)", f"{api} uses of MsgSend")
check(os.path.exists(os.path.join(ROOT, "image", "ram.build")), "a QNX buildfile is in the repository", "image/ram.build")
check(os.path.exists(os.path.join(ROOT, "docs", "codelab-qnx-on-apple-silicon.md")), "the Codelab is in the repository")

# ---- things that must not be in the repository ---------------------------------------------------
print(f"\n{B}Hygiene{X}")
code, files = sh(["git", "ls-files"])
tracked = files.splitlines()
elf = []
big = []
secrets = []
for f in tracked:
    p = os.path.join(ROOT, f)
    try:
        size = os.path.getsize(p)
        with open(p, "rb") as fh:
            head = fh.read(4)
            data = fh.read(400000) if size < 400000 else b""
    except OSError:
        continue
    if head == b"\x7fELF" or f.endswith((".ifs", ".kev", ".bin")):
        elf.append(f)
    if size > 5_000_000:
        big.append(f)
    if re.search(rb"gh[pous]_[A-Za-z0-9]{20,}|BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY|AKIA[0-9A-Z]{16}", head + data) or f.endswith((".env", ".pem")):
        secrets.append(f)
check(not elf, "no binaries or QNX images committed (the SDK is not ours to redistribute)", ", ".join(elf[:3]), "git rm --cached <file>")
check(not big, "no file over 5 MB", ", ".join(big[:3]))
check(not secrets, "no keys, tokens or .env files committed", ", ".join(secrets[:3]), "remove them and rotate the secret", )
bad = []
for f in tracked:
    if f.endswith((".png", ".gif", ".svg", ".json", ".xml")) and os.path.getsize(os.path.join(ROOT, f)) > 400000:
        continue
    t = read(f)
    if re.search(r"claude|anthropic|co-authored-by|generated with", t, re.I):
        bad.append(f)
code, msgs = sh(["git", "log", "--format=%B"])
check(not bad and not re.search(r"claude|anthropic|co-authored|generated", msgs, re.I),
      "no AI-tool attribution in files or commit messages (your preference)", ", ".join(bad[:3]))

# ---- links and tests ------------------------------------------------------------------------------
missing = []
for f in [t for t in tracked if t.endswith(".md")]:
    base = os.path.dirname(f)
    for mm in re.finditer(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", read(f)):
        t = mm.group(1)
        if t.startswith(("http://", "https://", "mailto:")):
            continue
        if not os.path.exists(os.path.normpath(os.path.join(ROOT, base, t))):
            missing.append(f"{f} -> {t}")
check(not missing, "every relative link in the documentation resolves", "; ".join(missing[:3]))
code, out = sh([sys.executable, "-m", "unittest", "discover", "-s", "tests"], 120)
check(code == 0, "the tests pass", out.splitlines()[-1] if out else "")

# ---- the Codelab URL ---------------------------------------------------------------------------------
if slug:
    print(f"\n{B}For the Devpost form{X}")
    print(f"  Repository URL : https://github.com/{slug}")
    print(f"  Codelab URL    : https://github.com/{slug}/blob/main/docs/codelab-qnx-on-apple-silicon.md")

# ---- what only a person can do ---------------------------------------------------------------------------
deadline = datetime.datetime(2026, 12, 15, 14, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=-5)))
left = deadline - datetime.datetime.now(datetime.timezone.utc)
print(f"\n{B}Still yours to do{X}  {D}(deadline Dec 15, 2:00 pm ET: {left.days} days left; aim for Dec 14){X}")
for t in ("record the demo video: under 3 minutes, shows it running on QEMU, no QNX logo or other logos, no copyrighted music",
          "upload it to YouTube as Public and check it plays when you are logged out",
          "fill the Devpost form from .notes/devpost/ (the AI-tools answer must be accurate)",
          "category: Developer Tooling & Host Tools; paste the Codelab URL for the bonus",
          "submit before the deadline and keep the confirmation"):
    print(f"  [ ] {t}")

print()
if failures:
    print(f"{R}{failures} check(s) failed.{X} Fix them, then run ./siege presubmit again.")
    sys.exit(1)
print(f"{G}All checks passed.{X}")

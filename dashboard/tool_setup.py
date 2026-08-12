"""
dashboard/tool_setup.py
=========================
One-time bootstrap for fpocket and P2Rank on Streamlit Cloud (Linux).

Neither tool is a simple apt package `packages.txt` can install on its
own:
  - fpocket has no guaranteed apt package across Debian base images —
    building from source (same method your own reference sheet already
    documents) is the reliable path.
  - P2Rank isn't an apt package at all — it's a downloadable Java
    release tarball. packages.txt can only provide the Java runtime it
    needs, not P2Rank itself.

This module builds/downloads both into a local `tools/` folder the
FIRST time the app starts on a fresh container, then reuses them on
every subsequent call — it's safe to import and call every time, it
no-ops instantly if the tools already exist.

IMPORTANT — add this to packages.txt in your repo root:
    build-essential
    git
    wget
    openjdk-17-jdk-headless

Installs are done into tools/ (NOT /usr/local) deliberately — Streamlit
Cloud containers do not run as root, so a system-wide `make install`
will fail on permissions. Everything here is user-writable.
"""

import os
import subprocess
import tarfile
import requests

TOOLS_DIR   = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tools")
FPOCKET_BIN = os.path.join(TOOLS_DIR, "fpocket", "bin", "fpocket")
P2RANK_DIR  = os.path.join(TOOLS_DIR, "p2rank")
P2RANK_BIN  = os.path.join(P2RANK_DIR, "prank")

# Pin an exact P2Rank version rather than "latest" — reproducibility
# matters for a report/viva; you don't want results changing silently
# because a new P2Rank release shipped a different model mid-semester.
P2RANK_RELEASE_URL = (
    "https://github.com/rdk/p2rank/releases/download/2.4.2/"
    "p2rank_2.4.2.tar.gz"
)


def ensure_fpocket_installed():
    """
    Builds fpocket from source into tools/fpocket if not already present.
    Returns the path to the binary, or None if the build failed (e.g.
    no C compiler available — this happens on plain Windows, which is
    expected and fine; fpocket simply won't be available there and the
    cascade in input_layer.py falls through to Method 4).
    """
    if os.path.exists(FPOCKET_BIN):
        return FPOCKET_BIN

    os.makedirs(TOOLS_DIR, exist_ok=True)
    src_dir = os.path.join(TOOLS_DIR, "fpocket_src")

    if not os.path.exists(src_dir):
        subprocess.run(
            ["git", "clone", "https://github.com/Discngine/fpocket.git", src_dir],
            check=True, capture_output=True
        )

    subprocess.run(["make"], cwd=src_dir, check=True, capture_output=True)

    install_prefix = os.path.join(TOOLS_DIR, "fpocket")
    subprocess.run(
        ["make", "install", f"PREFIX={install_prefix}"],
        cwd=src_dir, check=True, capture_output=True
    )

    return FPOCKET_BIN if os.path.exists(FPOCKET_BIN) else None


def ensure_p2rank_installed():
    """
    Downloads and extracts a pinned P2Rank release into tools/p2rank
    if not already present. Returns the path to the `prank` launcher
    script, or None if the download/extract failed.
    """
    if os.path.exists(P2RANK_BIN):
        return P2RANK_BIN

    os.makedirs(TOOLS_DIR, exist_ok=True)
    tar_path = os.path.join(TOOLS_DIR, "p2rank.tar.gz")

    r = requests.get(P2RANK_RELEASE_URL, stream=True, timeout=120)
    r.raise_for_status()
    with open(tar_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)

    with tarfile.open(tar_path) as tar:
        tar.extractall(TOOLS_DIR)

    # The extracted folder name includes the version string (e.g.
    # p2rank_2.4.2/) — rename it to a stable path so input_layer.py
    # always finds the same location regardless of version.
    extracted = [d for d in os.listdir(TOOLS_DIR)
                 if d.startswith("p2rank_") and os.path.isdir(os.path.join(TOOLS_DIR, d))]
    if extracted:
        os.rename(os.path.join(TOOLS_DIR, extracted[0]), P2RANK_DIR)

    os.remove(tar_path)

    if os.path.exists(P2RANK_BIN):
        os.chmod(P2RANK_BIN, 0o755)  # ensure it's executable after extraction
        return P2RANK_BIN
    return None

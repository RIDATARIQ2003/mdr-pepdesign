"""
dashboard/github_docking.py
=============================
Dashboard-side glue for the GitHub Actions docking pipeline. Uses the
GitHub REST API directly (just `requests`, no extra library) to push
job input files, trigger the workflow, and poll for results — all
through the repo's own file history, so there's no size limit to worry
about and no separate artifact-download step needed.

SETUP — add this to your Streamlit secrets (.streamlit/secrets.toml
locally, or the Secrets panel in Streamlit Cloud's settings):

    [github]
    token = "ghp_..."           # Personal Access Token, scopes: repo, workflow
    owner = "your-github-username"
    repo  = "mdr-pepdesign"
"""

import base64
import json
import uuid
import requests
import streamlit as st

API_ROOT = "https://api.github.com"


def _headers():
    return {
        "Authorization": f"Bearer {st.secrets['github']['token']}",
        "Accept": "application/vnd.github+json",
    }


def _repo_path():
    return f"{st.secrets['github']['owner']}/{st.secrets['github']['repo']}"


def _put_file(path, content_text, message):
    """Create or update a single file in the repo via the Contents API."""
    url = f"{API_ROOT}/repos/{_repo_path()}/contents/{path}"
    content_b64 = base64.b64encode(content_text.encode()).decode()

    # If the file already exists we need its current sha to update it —
    # without this GitHub rejects the write as a conflict.
    existing = requests.get(url, headers=_headers(), timeout=30)
    sha = existing.json().get("sha") if existing.status_code == 200 else None

    payload = {"message": message, "content": content_b64}
    if sha:
        payload["sha"] = sha

    r = requests.put(url, headers=_headers(), json=payload, timeout=30)
    r.raise_for_status()


def push_job_files(receptor_pdbqt: str, vina_config: str, ligands: dict) -> str:
    """
    Pushes every input file for a new docking job into jobs/{job_id}/
    and returns the job_id to use for triggering and polling.

    ligands: {pep_id: folded_pdb_text} — one entry per peptide to dock
    """
    job_id = uuid.uuid4().hex[:10]

    _put_file(f"jobs/{job_id}/receptor.pdbqt", receptor_pdbqt,
              f"Docking job {job_id}: receptor")
    _put_file(f"jobs/{job_id}/vina_config.txt", vina_config,
              f"Docking job {job_id}: vina config")

    for pep_id, pdb_text in ligands.items():
        _put_file(f"jobs/{job_id}/ligands/{pep_id}.pdb", pdb_text,
                   f"Docking job {job_id}: ligand {pep_id}")

    return job_id


def trigger_docking_workflow(job_id: str, branch: str = "main"):
    """Kicks off .github/workflows/dock.yml with this job_id."""
    url = f"{API_ROOT}/repos/{_repo_path()}/actions/workflows/dock.yml/dispatches"
    payload = {"ref": branch, "inputs": {"job_id": job_id}}
    r = requests.post(url, headers=_headers(), json=payload, timeout=30)
    r.raise_for_status()


def _get_file_content(path):
    """Returns decoded text content of a repo file, or None if it doesn't exist yet."""
    url = f"{API_ROOT}/repos/{_repo_path()}/contents/{path}"
    r = requests.get(url, headers=_headers(), timeout=30)
    if r.status_code != 200:
        return None
    content_b64 = r.json()["content"]
    return base64.b64decode(content_b64).decode()


def poll_job_status(job_id: str) -> dict:
    """
    Returns the parsed status.json from the job. Before the workflow has
    even started writing it, returns a default 'queued' status instead
    of erroring — the file genuinely doesn't exist yet at that point.
    """
    content = _get_file_content(f"jobs/{job_id}/results/status.json")
    if content is None:
        return {"stage": "queued", "done": False}
    return json.loads(content)


def fetch_docking_results(job_id: str):
    """Returns docking_scores.csv content as text, once the job is done."""
    return _get_file_content(f"jobs/{job_id}/results/docking_scores.csv")

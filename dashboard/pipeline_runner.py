"""
pipeline_runner.py
====================
Generalized, automated version of today's validated EmrE pipeline -
runs the SAME steps, just driven by a target protein + peptide set
instead of hardcoded EmrE values.

DOES NOT MODIFY ANY EXISTING SCRIPT. This is new code that calls the
same logic patterns as batch_dock_local.py / build_complexes.py, kept
separate so nothing already working can break.

WHY THIS EXISTS:
new_run.py currently only fetches a structure and detects the pocket -
it stops there. This module picks up from where new_run.py leaves off
and runs the rest of the validated pipeline: receptor prep, ligand prep,
box sizing, and docking - automatically, for any protein.

DESIGN NOTE - WHY THIS RUNS AS A BACKGROUND PROCESS, NOT INLINE:
Streamlit blocks the UI while a button's callback runs. Docking 300+
peptides takes hours. Running that inline would freeze the page and
likely hit a server timeout. Instead, this module launches the real
work as a separate OS process (subprocess.Popen, non-blocking) that
writes its progress to a JSON status file. The Streamlit page (see
new_run.py's "Automated Run" tab) polls that file and shows live
progress without blocking - the same separation Jupyter notebooks
naturally have (cell runs in the kernel, you can still look at other
cells) but explicit here since Streamlit reruns the whole script on
every interaction.

USAGE FROM A STREAMLIT PAGE:
    from pipeline_runner import start_pipeline_job, get_job_status

    job_id = start_pipeline_job(
        protein_pdb_path="data/clean_protein.pdb",
        pocket_coords={"cx":..., "cy":..., "cz":...},
        peptide_folded_dir="data/folded",
        project_root=r"D:\\mdr-pepdesign"
    )
    # later, on each Streamlit rerun:
    status = get_job_status(job_id)
    # status = {"stage": "...", "progress": 0.42, "done": False, "log": [...]}
"""

import os
import sys
import json
import glob
import time
import subprocess
import uuid
from datetime import datetime

JOBS_DIR = "pipeline_jobs"  # status files live here, one per run


def _job_status_path(job_id):
    return os.path.join(JOBS_DIR, f"{job_id}_status.json")


def _write_status(job_id, **kwargs):
    """Merge-update the status file so partial writes never lose prior fields."""
    path = _job_status_path(job_id)
    status = {}
    if os.path.exists(path):
        try:
            with open(path) as f:
                status = json.load(f)
        except (json.JSONDecodeError, OSError):
            status = {}
    status.update(kwargs)
    status["updated_at"] = datetime.now().isoformat()
    with open(path, "w") as f:
        json.dump(status, f, indent=2)


def get_job_status(job_id):
    """Read current status - safe to call from Streamlit on every rerun."""
    path = _job_status_path(job_id)
    if not os.path.exists(path):
        return {"stage": "not_found", "progress": 0.0, "done": False, "log": []}
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"stage": "reading_error", "progress": 0.0, "done": False, "log": []}


def list_jobs():
    """Return all known job IDs, most recent first - lets the UI show job history."""
    os.makedirs(JOBS_DIR, exist_ok=True)
    files = sorted(
        glob.glob(os.path.join(JOBS_DIR, "*_status.json")),
        key=os.path.getmtime, reverse=True
    )
    return [os.path.basename(f).replace("_status.json", "") for f in files]


def start_pipeline_job(protein_pdb_path, pocket_coords, peptide_folded_dir,
                         project_root, protein_name="target", vina_path=None):
    """
    Launches the full pipeline as a non-blocking background process.
    Returns a job_id immediately - the actual work happens in a
    separate Python process so the Streamlit page never blocks.
    """
    os.makedirs(JOBS_DIR, exist_ok=True)
    job_id = f"{protein_name}_{uuid.uuid4().hex[:8]}"

    _write_status(job_id,
        stage="queued", progress=0.0, done=False, error=None,
        log=["Job queued"], protein_name=protein_name,
        started_at=datetime.now().isoformat())

    worker_script = os.path.join(os.path.dirname(__file__), "_pipeline_worker.py")

    args = [
        sys.executable, worker_script,
        "--job_id", job_id,
        "--protein_pdb", protein_pdb_path,
        "--pocket_json", json.dumps(pocket_coords),
        "--folded_dir", peptide_folded_dir,
        "--project_root", project_root,
        "--jobs_dir", JOBS_DIR,
    ]
    if vina_path:
        args += ["--vina_path", vina_path]

    # Popen, not run() - this is the key non-blocking step. The parent
    # Streamlit process returns immediately; the worker keeps running
    # independently even as Streamlit reruns the page repeatedly while
    # the user watches progress.
    subprocess.Popen(args, cwd=project_root)

    return job_id

import subprocess
import os
import glob
import time

os.chdir(r"D:\mdr-pepdesign")
os.makedirs("docking/results", exist_ok=True)

VINA_PATH = r"D:\mdr-pepdesign\tools\vina_1.2.7_win.exe"
ligands = glob.glob("docking/ligands_rigid/*.pdbqt")
total = len(ligands)
done = 0
failed = []

# Progress log
LOG_FILE = "docking/docking_progress.log"

with open(LOG_FILE, "a", encoding="utf-8") as log:
    log.write("\n=============================\n")
    log.write("New docking session started\n")
    log.write(f"Total peptides: {total}\n")

print(f"Starting batch docking - {total} peptides")

for i, lig in enumerate(ligands):

    name = os.path.basename(lig).replace(".pdbqt", "")
    out = f"docking/results/{name}_out.pdbqt"

    # Resume support
    if os.path.exists(out):
        done += 1

        with open(LOG_FILE, "a", encoding="utf-8") as log:
            log.write(f"SKIPPED: {name}\n")

        continue

    result = subprocess.run(
        [
            VINA_PATH,
            "--config", "docking/vina.conf",
            "--ligand", lig,
            "--out", out,
            "--cpu", "1"          # Reduced CPU usage
        ],
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        done += 1

        with open(LOG_FILE, "a", encoding="utf-8") as log:
            log.write(f"SUCCESS: {name}\n")

    else:
        failed.append(name)

        with open(LOG_FILE, "a", encoding="utf-8") as log:
            log.write(f"FAILED: {name}\n")
            log.write(result.stderr + "\n")

    if (i + 1) % 10 == 0:
        print(f"Progress: {i + 1}/{total} - Done: {done} - Failed: {len(failed)}")

    # Give the PC a short break every 20 peptides
    if (i + 1) % 20 == 0:
        print("\nCooling pause... waiting 10 seconds.\n")
        time.sleep(10)

print(f"\nDocked: {done} - Failed: {len(failed)}")

if failed:
    print("Failed peptides:")
    print(failed[:5])

with open(LOG_FILE, "a", encoding="utf-8") as log:
    log.write(f"\nFinished. Success: {done}, Failed: {len(failed)}\n")
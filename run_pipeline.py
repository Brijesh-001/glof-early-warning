"""
GEWS — end-to-end pipeline runner.
Connects the stages: data -> model -> evaluation. Run from the repo root.

    python run_pipeline.py            # full chain (model scoring ~9 min first time)
    python run_pipeline.py --eval     # skip modelling, just re-evaluate committed scores
    python run_pipeline.py --tests    # just the evaluation unit tests

    python run_pipeline.py --update   # fetch the newest finished windows, re-score, re-evaluate (needs
                                      #   requirements-collect.txt; see collect/README.md)
        --skip-fetch                  #   re-score the data files as they are (no download)
        --dry-run | --verify          #   only the fetch step, writing nothing (see collect/gews_collect.py)
        --lake NAME  (repeatable)     #   limit the fetch to some lakes

Each stage reads the previous stage's output folder, so the data flow is explicit.
"""
import subprocess, sys, os

ROOT = os.path.dirname(os.path.abspath(__file__))


def run(cmd, cwd):
    print(f"\n$ (cd {cwd}) {' '.join(cmd)}")
    subprocess.run(cmd, cwd=os.path.join(ROOT, cwd), check=True)


def model_stage():
    # B: score every lake from the data cube -> models/outputs/
    run([sys.executable, "gews_spec.py", "../data/lake_data", "outputs"], "models")
    # B2: v2 fusion + calibration on top of the per-signal scores (peer-relative, corroborated,
    # budget-calibrated); overwrites anomaly_scores_all_lakes.csv, keeps v1 as anomaly_scores_v1.csv
    run([sys.executable, "gews_v2.py", "../data/lake_data", "outputs"], "models")


def collect_stage(extra):
    """Fetch the newest finished windows. Exit code 1 = some lakes failed (carry on with the rest);
    2 or more = the step could not run at all (stop)."""
    cmd = [sys.executable, "collect/gews_collect.py", *extra]
    print(f"\n[stage] fetch new windows\n$ {' '.join(cmd)}")
    rc = subprocess.run(cmd, cwd=ROOT).returncode
    if rc >= 2:
        sys.exit(f"[fetch] could not run (exit {rc}). Nothing was changed.")
    if rc == 1:
        print("[fetch] some lakes failed: they keep their old data and show as behind. See data/update_log.json.")


def update_model_stage():
    # production detector only (the slow detector comparison keeps its last full result), then v2
    print("\n[stage] re-score every lake")
    run([sys.executable, "gews_spec.py", "../data/lake_data", "outputs", "--fast"], "models")
    run([sys.executable, "gews_v2.py", "../data/lake_data", "outputs"], "models")


def eval_stage():
    # C: metrics + Sikkim test, then the leak check + unseen-lake test
    run([sys.executable, "gews_evaluation.py"], "evaluation")
    run([sys.executable, "gews_leak_gen.py"], "evaluation")


def tests_stage():
    run([sys.executable, "-m", "pytest", "test_evaluation.py", "-q"], "evaluation")


def update_main(argv):
    passthrough, skip, i = [], False, 0
    only_fetch = any(a in argv for a in ("--dry-run", "--verify"))
    while i < len(argv):
        a = argv[i]
        if a == "--update":
            pass
        elif a == "--skip-fetch":
            skip = True
        elif a in ("--lake", "--margin-days", "--today", "--workers"):
            passthrough += [a, argv[i + 1]]; i += 1
        elif a in ("--dry-run", "--verify", "--refresh-velocity"):
            passthrough.append(a)
        else:
            sys.exit(f"unknown option for --update: {a}")
        i += 1
    if only_fetch:                      # preview / check: never touch the scores
        collect_stage(passthrough); return
    if not skip:
        collect_stage(passthrough)
    update_model_stage()
    print("\n[stage] evaluation")
    eval_stage()
    tests_stage()
    print("\n[done] data, scores and evaluation are up to date. Refresh the dashboard.")


def main():
    if "--update" in sys.argv[1:]:
        update_main(sys.argv[1:]); return
    args = set(sys.argv[1:])
    if args == {"--tests"}:
        tests_stage(); return
    if args == {"--eval"}:
        eval_stage(); tests_stage(); return
    # full chain
    model_stage()
    eval_stage()
    tests_stage()
    print("\n[done] model + evaluation complete. See models/outputs/ and evaluation/outputs/.")


if __name__ == "__main__":
    main()

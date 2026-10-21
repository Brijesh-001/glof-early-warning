"""
GEWS — end-to-end pipeline runner.
Connects the stages: data -> model -> evaluation. Run from the repo root.

    python run_pipeline.py            # full chain (model scoring ~9 min first time)
    python run_pipeline.py --eval     # skip modelling, just re-evaluate committed scores
    python run_pipeline.py --tests    # just the evaluation unit tests

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


def eval_stage():
    # C: metrics + Sikkim test, then the leak check + unseen-lake test
    run([sys.executable, "gews_evaluation.py"], "evaluation")
    run([sys.executable, "gews_leak_gen.py"], "evaluation")


def tests_stage():
    run([sys.executable, "-m", "pytest", "test_evaluation.py", "-q"], "evaluation")


def main():
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

"""Create a new blind-test directory containing installed runtime files only."""
import argparse
import shutil
from pathlib import Path


def prepare(installed, case):
    if case.exists():
        raise ValueError("Use a new empty-case path for each independent trial")
    runtime = ("SKILL.md", "workflow.md", "references/review-input.md",
               "scripts/product_filing_model.py", "scripts/industrial_model.py", "references/industrial-project.md", "references/product-project.md", "references/filing-recognition.md",
               "scripts/analyze.py", "scripts/position_policy.py", "scripts/fixed_model.py", "scripts/check_filing_rows.py",
               "scripts/stable_review.py", "scripts/review_contribution.py")
    for name in runtime:
        if not (installed / name).is_file():
            raise FileNotFoundError(installed / name)
    for name in runtime:
        target = case / "skill" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(installed / name, target)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("installed", type=Path)
    parser.add_argument("case", type=Path)
    args = parser.parse_args()
    prepare(args.installed, args.case)



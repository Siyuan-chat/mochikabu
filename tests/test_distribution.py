from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]

DISTRIBUTED_PATHS = [
    "SKILL.md",
    "scripts/analyze.py",
    "scripts/fetch_public.py",
    "scripts/value_public.py",
    "references/architecture.md",
    "references/decision-rules.md",
    "references/pseudocode.md",
    "references/public-research.md",
    "references/sources.md",
    "examples/config.example.json",
    "examples/holdings_snapshot.example.json",
    "examples/output.example.json",
]


class DistributionSyncTests(unittest.TestCase):
    def test_agent_skill_distribution_matches_source(self):
        skill_root = ROOT / "skills" / "mochikabu"
        for relative in DISTRIBUTED_PATHS:
            with self.subTest(path=relative):
                source = ROOT / relative
                packaged = skill_root / relative
                self.assertTrue(packaged.exists(), f"missing packaged file: {packaged}")
                self.assertEqual(
                    source.read_bytes(),
                    packaged.read_bytes(),
                    f"packaged skill drifted from source: {relative}",
                )


if __name__ == "__main__":
    unittest.main()

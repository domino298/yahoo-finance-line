import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github" / "workflows"


class WorkflowConfigurationTest(unittest.TestCase):
    def test_only_current_workflow_has_a_schedule(self):
        scheduled = []
        for path in WORKFLOW_DIR.glob("*.yml"):
            if "schedule:" in path.read_text(encoding="utf-8"):
                scheduled.append(path.name)
        self.assertEqual(scheduled, ["pages-mobile-refresh3.yml"])

    def test_generated_commit_does_not_trigger_same_workflow(self):
        text = (WORKFLOW_DIR / "pages-mobile-refresh3.yml").read_text(encoding="utf-8")
        self.assertNotIn("  push:", text)
        self.assertIn('cron: "*/15 0-8 * * 1-5"', text)
        self.assertIn("cancel-in-progress: true", text)


if __name__ == "__main__":
    unittest.main()

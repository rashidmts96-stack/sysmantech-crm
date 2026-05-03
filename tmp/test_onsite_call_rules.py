import unittest

from onsite_calls_blueprint import ALLOWED_TRANSITIONS, STATUSES


class OnsiteCallRuleTests(unittest.TestCase):
    def test_expected_statuses_exist(self):
        self.assertIn("New Lead", STATUSES)
        self.assertIn("Assigned", STATUSES)
        self.assertIn("Completed", STATUSES)
        self.assertIn("Failed", STATUSES)

    def test_open_can_transition_to_assigned(self):
        self.assertIn("Assigned", ALLOWED_TRANSITIONS["Open"])

    def test_in_progress_can_transition_to_completed(self):
        self.assertIn("Completed", ALLOWED_TRANSITIONS["In Progress"])

    def test_completed_cannot_transition_back_to_open(self):
        self.assertNotIn("Open", ALLOWED_TRANSITIONS["Completed"])

    def test_cancelled_has_no_forward_transitions(self):
        self.assertEqual(set(), ALLOWED_TRANSITIONS["Cancelled"])


if __name__ == "__main__":
    unittest.main()

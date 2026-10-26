import unittest

from apply_agent import already_applied, fit_job, location_ok, map_field


class JobScoutSafetyTests(unittest.TestCase):
    def setUp(self):
        self.profile = {
            "first_name": "Alex",
            "last_name": "Example",
            "email": "alex@example.com",
            "authorized_to_work": "Yes",
            "requires_sponsorship": "No",
            "preferred_locations": ["Bengaluru", "Hyderabad", "India"],
            "target_roles": ["Junior Java Developer", "Python Developer", "Backend Developer"],
            "skills": ["Java", "Python", "SQL"]
        }

    def test_india_role_passes_location_filter(self):
        self.assertTrue(location_ok("Bangalore, India", self.profile["preferred_locations"]))

    def test_us_remote_role_is_excluded(self):
        self.assertFalse(location_ok("Remote — United States", self.profile["preferred_locations"]))

    def test_resume_skills_affect_match_score(self):
        job = {
            "title": "Python Developer",
            "location": "Bangalore, India",
            "match_score": 80,
            "description": "Build Python services and SQL APIs with FastAPI."
        }
        result = fit_job(job, "Python SQL Java programming projects", self.profile)
        self.assertGreaterEqual(result["resume_match_score"], 65)
        self.assertIn("Python", result["overlapping_skills"])

    def test_demographic_question_is_never_inferred(self):
        answer, action = map_field("Please select your gender", self.profile, "Alex Example")
        self.assertIsNone(answer)
        self.assertEqual(action, "sensitive")

    def test_india_work_authorization_uses_explicit_profile_answer(self):
        answer, action = map_field("Are you legally authorized to work in India?", self.profile, "Alex Example")
        self.assertEqual((answer, action), ("Yes", "radio"))

    def test_foreign_country_authorization_is_not_reused(self):
        answer, action = map_field("Are you legally authorized to work in the United States?", self.profile, "Alex Example")
        self.assertIsNone(answer)
        self.assertEqual(action, "unknown")

    def test_foreign_sponsorship_question_is_not_guessed(self):
        answer, action = map_field("Will you require sponsorship to work in Canada?", self.profile, "Alex Example")
        self.assertIsNone(answer)
        self.assertEqual(action, "unknown")

    def test_previously_submitted_application_is_deduplicated(self):
        log = {"applications": [{
            "application_key": "https://jobs.lever.co/example/abc/apply",
            "status": "submitted"
        }]}
        self.assertTrue(already_applied(log, "https://jobs.lever.co/example/abc/apply?source=jobscout"))

    def test_manual_review_is_not_automatically_retried(self):
        log = {"applications": [{
            "apply_url": "https://jobs.lever.co/example/abc/apply",
            "status": "manual_review"
        }]}
        self.assertTrue(already_applied(log, "https://jobs.lever.co/example/abc/apply"))

    def test_unfinished_application_is_not_claimed_submitted(self):
        log = {"applications": [{
            "apply_url": "https://jobs.lever.co/example/abc/apply",
            "status": "ready_dry_run"
        }]}
        self.assertFalse(already_applied(log, "https://jobs.lever.co/example/abc/apply"))


if __name__ == "__main__":
    unittest.main()

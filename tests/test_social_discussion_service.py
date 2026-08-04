import unittest

from app.services.social_discussion_service import build_discussion_state, rank_featured_discussions, score_discussion_post


class SocialDiscussionServiceTests(unittest.TestCase):
    def test_relevance_ranks_operational_discussion_above_shallow_recent_post(self):
        now_ts = 1_700_000_000
        posts = [
            {
                "id": 1,
                "ticker": "F",
                "user": "ana",
                "user_id": 10,
                "text": "top",
                "timestamp": now_ts - 60,
                "likes": 0,
                "reposts": 0,
                "comments": [],
            },
            {
                "id": 2,
                "ticker": "F",
                "user": "bruno",
                "user_id": 11,
                "text": "F rejeitou resistencia com volume alto; risco e invalidacao ficam no suporte da VWAP.",
                "timestamp": now_ts - 7200,
                "likes": 3,
                "reposts": 1,
                "comments": [{"id": 1}],
            },
        ]

        ranked = rank_featured_discussions("F", posts, now_ts=now_ts)

        self.assertEqual(ranked[0]["id"], 2)
        self.assertGreater(ranked[0]["discussion_relevance_score"], ranked[1]["discussion_relevance_score"])
        self.assertIn("operational_terms", ranked[0]["discussion_relevance_reason"])

    def test_mismatched_ticker_is_not_featured(self):
        ranked = rank_featured_discussions(
            "PETR4",
            [
                {"id": 1, "ticker": "AAPL", "text": "AAPL com volume", "user_id": 1},
                {"id": 2, "ticker": "PETR4", "text": "PETR4 sem novidade", "user_id": 2},
            ],
        )

        self.assertEqual([item["id"] for item in ranked], [2])

    def test_empty_discussion_state_is_explicit(self):
        state = build_discussion_state("AAPL", [])

        self.assertEqual(state["status"], "empty")
        self.assertIn("Sem discussao real para AAPL", state["message"])

    def test_score_exposes_reasons(self):
        relevance = score_discussion_post(
            "AAPL",
            {
                "ticker": "AAPL",
                "text": "AAPL rompeu resistencia com fluxo e volume.",
                "likes": 2,
                "comments": [{}],
            },
            now_ts=1_700_000_000,
        )

        self.assertGreater(relevance["score"], 40)
        self.assertIn("ticker_match", relevance["reasons"])
        self.assertIn("engagement", relevance["reasons"])


if __name__ == "__main__":
    unittest.main()

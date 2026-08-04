"""Missao 34 — testes focados de performance, escala e resiliencia.

Cobre o fix do N+1 de I/O em get_posts (2N leituras+parses do
moderation_state.json por request -> 2 por request):
- equivalencia EXATA entre is_post_hidden e get_hidden_post_ids;
- equivalencia EXATA entre get_user_guardian_score e get_user_guardian_scores;
- contagem de leituras do estado (helpers em lote leem 1 vez).
"""

from __future__ import annotations

import json
import random
import tempfile
import time
import unittest
from pathlib import Path

from app.social import moderation


REVIEW_ACTIONS = ["hide", "remove", "approve", "dismiss", "warn", ""]


def _write_state(state: dict) -> None:
    moderation.MODERATION_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    moderation.MODERATION_STORE_PATH.write_text(
        json.dumps(state), encoding="utf-8"
    )


def _random_state(rng: random.Random, post_ids: list) -> dict:
    reviewed = [
        {
            "post_id": rng.choice(post_ids + [None, 999_999]),
            "action": rng.choice(REVIEW_ACTIONS),
        }
        for _ in range(rng.randint(20, 60))
    ]
    queue = [
        {
            "post_id": rng.choice(post_ids + [None, 888_888]),
            "auto_hidden": rng.random() < 0.5,
        }
        for _ in range(rng.randint(20, 60))
    ]
    return {"reviewed_reports": reviewed, "review_queue": queue}


class Mission34ModerationBatchTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._original_path = moderation.MODERATION_STORE_PATH
        moderation.MODERATION_STORE_PATH = (
            Path(self._tmp.name) / "moderation_state.json"
        )

    def tearDown(self):
        moderation.MODERATION_STORE_PATH = self._original_path
        self._tmp.cleanup()

    # ------------------------------------------------------------------
    # Equivalencia funcional (protocolo de regressao da Missao 34)
    # ------------------------------------------------------------------

    def test_get_hidden_post_ids_equivalent_to_is_post_hidden(self):
        rng = random.Random(3401)
        candidate_ids = list(range(1, 41)) + [None, 999_999, 888_888, 777]

        for round_index in range(20):
            _write_state(_random_state(rng, list(range(1, 41))))
            batch = moderation.get_hidden_post_ids(candidate_ids)
            for post_id in candidate_ids:
                self.assertEqual(
                    post_id in batch,
                    moderation.is_post_hidden(post_id),
                    f"divergencia round={round_index} post_id={post_id}",
                )

    def test_get_hidden_post_ids_empty_input(self):
        _write_state({"reviewed_reports": [], "review_queue": []})
        self.assertEqual(moderation.get_hidden_post_ids([]), set())

    def test_get_user_guardian_scores_equivalent(self):
        _write_state({"reviewed_reports": [], "review_queue": []})
        # cria registros reais de score via API publica
        for user_id in (11, 22, 33):
            moderation.record_content_approved(
                user_id, content_type="post", content_id=user_id, post_id=user_id
            )
        moderation.record_post_removed(22, target_user_id=22, reason="test")

        user_ids = [11, 22, 33, 44, 0, None]
        batch = moderation.get_user_guardian_scores(user_ids)
        for user_id in user_ids:
            self.assertEqual(
                batch[user_id],
                moderation.get_user_guardian_score(user_id),
                f"divergencia user_id={user_id}",
            )

    # ------------------------------------------------------------------
    # Contagem de I/O: lote le o estado UMA vez (o proprio N+1)
    # ------------------------------------------------------------------

    def test_batch_helpers_read_state_once(self):
        _write_state(_random_state(random.Random(3402), list(range(1, 201))))
        calls = {"n": 0}
        original_read = moderation.read_json_file

        def counting_read(*args, **kwargs):
            calls["n"] += 1
            return original_read(*args, **kwargs)

        moderation.read_json_file = counting_read
        try:
            calls["n"] = 0
            moderation.get_hidden_post_ids(list(range(1, 201)))
            self.assertEqual(calls["n"], 1, "get_hidden_post_ids deve ler 1 vez")

            calls["n"] = 0
            moderation.get_user_guardian_scores(list(range(1, 201)))
            self.assertEqual(
                calls["n"], 1, "get_user_guardian_scores deve ler 1 vez"
            )

            # comportamento por chamada (o bug original): 3 chamadas = 3 leituras
            calls["n"] = 0
            for post_id in (1, 2, 3):
                moderation.is_post_hidden(post_id)
            self.assertEqual(calls["n"], 3)
        finally:
            moderation.read_json_file = original_read

    def test_batch_timing_evidence(self):
        _write_state(_random_state(random.Random(3403), list(range(1, 301))))
        ids = list(range(1, 301))

        start = time.perf_counter()
        for post_id in ids:
            moderation.is_post_hidden(post_id)
        per_call = time.perf_counter() - start

        start = time.perf_counter()
        moderation.get_hidden_post_ids(ids)
        batch = time.perf_counter() - start

        print(
            f"\n[M34 evidencia] is_post_hidden x300={per_call:.4f}s | "
            f"get_hidden_post_ids(300)={batch:.4f}s"
        )


if __name__ == "__main__":
    unittest.main()

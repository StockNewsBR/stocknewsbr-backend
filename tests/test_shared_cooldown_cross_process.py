import concurrent.futures
import multiprocessing
import tempfile
import time
import unittest
from pathlib import Path

from app.services import symbol_sanitizer
from app.services.public_market_data_service import _symbol_aliases, _symbol_aliases_cached


def _process_writer_func(cooldown_path_str: str, symbol: str):
    from app.services import symbol_sanitizer
    symbol_sanitizer._COOLDOWN_FILE = Path(cooldown_path_str)
    symbol_sanitizer.mark_symbol_cooldown(symbol, seconds=120)


class SharedCooldownCrossProcessTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cooldown_file = Path(self.temp_dir.name) / "test_symbol_cooldowns.json"
        self.original_cooldown_file = symbol_sanitizer._COOLDOWN_FILE
        symbol_sanitizer._COOLDOWN_FILE = self.cooldown_file
        with symbol_sanitizer._lock:
            symbol_sanitizer._cooldowns.clear()
            symbol_sanitizer._shared_file_sig = None
            symbol_sanitizer._last_shared_sync = 0.0

    def tearDown(self):
        symbol_sanitizer._COOLDOWN_FILE = self.original_cooldown_file
        with symbol_sanitizer._lock:
            symbol_sanitizer._cooldowns.clear()
            symbol_sanitizer._shared_file_sig = None
            symbol_sanitizer._last_shared_sync = 0.0
        self.temp_dir.cleanup()

    def test_1_cooldown_visible_across_simulated_instances(self):
        """1. Cooldown marcado por uma instância é imediatamente visível para outra instância."""
        # Instância A marca cooldown
        symbol_sanitizer.mark_symbol_cooldown("PETR4", reason="provider_rate_limit", seconds=120)
        self.assertTrue(symbol_sanitizer.is_symbol_on_cooldown("PETR4"))
        self.assertTrue(self.cooldown_file.exists())

        # Instância B (simulando limpa de estado em memória local)
        with symbol_sanitizer._lock:
            symbol_sanitizer._cooldowns.clear()
            symbol_sanitizer._shared_file_sig = None
            symbol_sanitizer._last_shared_sync = 0.0

        # Instância B lê do shared store
        self.assertTrue(symbol_sanitizer.is_symbol_on_cooldown("PETR4"))

    def test_2_ttl_expires_correctly(self):
        """2. TTL expira e o símbolo deixa de estar em cooldown após o tempo estipulado."""
        now = time.time()
        symbol_sanitizer.mark_symbol_cooldown("VALE3", seconds=60)
        self.assertTrue(symbol_sanitizer.is_symbol_on_cooldown("VALE3", now=now))

        # Após 65 segundos o cooldown de 60s deve ter expirado
        self.assertFalse(symbol_sanitizer.is_symbol_on_cooldown("VALE3", now=now + 65.0))

    def test_3_concurrent_writes_do_not_corrupt_state(self):
        """3. Múltiplas gravações concorrentes não corrompem o estado nem o JSON compartilhado."""
        def _writer(index: int):
            symbol_sanitizer.mark_symbol_cooldown(f"TEST{index}", seconds=60)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(_writer, i) for i in range(50)]
            concurrent.futures.wait(futures)

        # Deve ler com sucesso o JSON gerado sem erros de parse
        snapshot = symbol_sanitizer.symbol_cooldown_snapshot()
        self.assertGreaterEqual(len(snapshot), 50)

    def test_4_fallback_local_continues_functional_if_shared_store_fails(self):
        """4. Se o shared store falhar (ex: diretório inválido/permissão), o fallback local funciona sem exceção."""
        symbol_sanitizer._COOLDOWN_FILE = Path("/invalid_dir_31f_cross_process/test.json")
        symbol_sanitizer.mark_symbol_cooldown("ITUB4", seconds=60)
        self.assertTrue(symbol_sanitizer.is_symbol_on_cooldown("ITUB4"))

    def test_5_alias_memoization_remains_pure_and_separate_from_side_effects(self):
        """5. Expansão pura de aliases (_symbol_aliases_cached) continua pura e separada do efeito colateral (Finding 9)."""
        _symbol_aliases_cached.cache_clear()

        aliases1 = _symbol_aliases("PETR4")
        self.assertIn("PETR4", aliases1)

        info_before = _symbol_aliases_cached.cache_info()
        aliases2 = _symbol_aliases("PETR4")
        info_after = _symbol_aliases_cached.cache_info()

        # O lru_cache deve ter um hit
        self.assertGreater(info_after.hits, info_before.hits)
        self.assertEqual(aliases1, aliases2)

        # Símbolo inválido dispara mark_symbol_cooldown fora da função pura
        invalid_aliases = _symbol_aliases("INVALID_SYMBOL_12345_XYZ")
        self.assertEqual(invalid_aliases, [])
        self.assertTrue(symbol_sanitizer.is_symbol_on_cooldown("INVALID_SYMBOL_12345_XYZ"))

    def test_6_real_os_processes_concurrent_writes_no_lost_update(self):
        """6. Dois PROCESSOS OS independentes gravam símbolos diferentes simultaneamente no shared store sem lost update."""
        symbol_sanitizer.mark_symbol_cooldown("PETR4", seconds=120)

        ctx = multiprocessing.get_context("spawn")
        p1 = ctx.Process(target=_process_writer_func, args=(str(self.cooldown_file), "VALE3"))
        p2 = ctx.Process(target=_process_writer_func, args=(str(self.cooldown_file), "ITUB4"))

        p1.start()
        p2.start()
        p1.join(timeout=10)
        p2.join(timeout=10)

        self.assertEqual(p1.exitcode, 0)
        self.assertEqual(p2.exitcode, 0)

        with symbol_sanitizer._lock:
            symbol_sanitizer._cooldowns.clear()
            symbol_sanitizer._shared_file_sig = None
            symbol_sanitizer._last_shared_sync = 0.0

        snapshot = symbol_sanitizer.symbol_cooldown_snapshot()
        self.assertIn("PETR4", snapshot)
        self.assertIn("VALE3", snapshot)
        self.assertIn("ITUB4", snapshot)

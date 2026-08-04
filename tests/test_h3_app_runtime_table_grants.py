import os
import re
import unittest


_SQL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts",
    "sql",
    "h3_app_runtime_table_grants.sql",
)

# Mission 36 already covers these two tables with full RLS policies; this
# script must never touch them (that would duplicate/contradict scope).
RLS_SCOPED_TABLES = {"media_assets", "promo_redemptions"}

EXPECTED_TABLE_GRANTS = {
    "users": {"SELECT", "INSERT", "UPDATE"},
    "user_sessions": {"SELECT", "INSERT", "UPDATE"},
    "login_challenges": {"SELECT", "INSERT", "UPDATE"},
    "auth_audit_events": {"SELECT", "INSERT"},
    "referrals": {"SELECT", "INSERT", "UPDATE"},
    "referral_stats": {"SELECT", "INSERT", "UPDATE"},
    "telegram_link_tokens": {"SELECT", "INSERT", "UPDATE"},
    "subscription_audit_logs": {"SELECT", "INSERT"},
    "social_posts": {"SELECT", "INSERT", "UPDATE", "DELETE"},
    "social_comments": {"SELECT", "INSERT", "UPDATE", "DELETE"},
    "social_likes": {"SELECT", "INSERT", "DELETE"},
    "social_reposts": {"SELECT", "INSERT", "DELETE"},
    "social_follows": {"SELECT", "INSERT", "DELETE"},
    "social_sentiment_votes": {"SELECT", "INSERT", "UPDATE"},
}

GRANT_LINE_RE = re.compile(
    r"^GRANT\s+([A-Z, ]+)\s+ON\s+public\.(\w+)\s+TO\s+([\w, ]+);\s*$",
    re.IGNORECASE,
)
SEQUENCE_GRANT_RE = re.compile(
    r"^GRANT\s+USAGE,\s*SELECT\s+ON\s+SEQUENCE\s+public\.(\w+)\s+TO\s+([\w, ]+);\s*$",
    re.IGNORECASE,
)


def _read_text():
    with open(_SQL_PATH, "r", encoding="utf-8") as handle:
        return handle.read()


def _strip_comments(sql):
    cleaned = []
    for line in sql.splitlines():
        marker = line.find("--")
        cleaned.append(line if marker == -1 else line[:marker])
    return "\n".join(cleaned)


class H3RuntimeTableGrantsSqlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = _read_text()
        cls.sql = _strip_comments(cls.raw)
        cls.lines = [line.strip() for line in cls.sql.splitlines() if line.strip()]
        cls.table_grants = {}
        cls.sequence_grants = {}
        for line in cls.lines:
            table_match = GRANT_LINE_RE.match(line)
            if table_match:
                verbs = {v.strip().upper() for v in table_match.group(1).split(",")}
                table = table_match.group(2).lower()
                roles = {r.strip().lower() for r in table_match.group(3).split(",")}
                cls.table_grants[table] = (verbs, roles)
                continue
            sequence_match = SEQUENCE_GRANT_RE.match(line)
            if sequence_match:
                sequence = sequence_match.group(1).lower()
                roles = {r.strip().lower() for r in sequence_match.group(2).split(",")}
                cls.sequence_grants[sequence] = roles

    def test_file_exists_and_is_nonempty(self):
        self.assertTrue(os.path.isfile(_SQL_PATH))
        self.assertGreater(len(self.raw), 0)

    def test_wrapped_in_single_transaction(self):
        upper_lines = [line.upper() for line in self.lines]
        self.assertEqual(upper_lines[0], "BEGIN;")
        self.assertEqual(upper_lines[-1], "COMMIT;")
        self.assertEqual(upper_lines.count("BEGIN;"), 1)
        self.assertEqual(upper_lines.count("COMMIT;"), 1)

    def test_never_touches_mission_36_rls_scoped_tables(self):
        self.assertTrue(RLS_SCOPED_TABLES.isdisjoint(self.table_grants))
        for table in RLS_SCOPED_TABLES:
            self.assertNotIn(table, self.sql.lower())

    def test_exact_table_grant_scope(self):
        self.assertEqual(set(self.table_grants), set(EXPECTED_TABLE_GRANTS))
        for table, expected_verbs in EXPECTED_TABLE_GRANTS.items():
            actual_verbs, actual_roles = self.table_grants[table]
            self.assertEqual(
                actual_verbs, expected_verbs, f"{table} verb mismatch: {actual_verbs}"
            )
            self.assertEqual(actual_roles, {"stocknewsbr_app", "stocknewsbr_worker"})

    def test_every_granted_table_has_a_matching_sequence_grant(self):
        # promo_codes-style withheld sequences aren't relevant here: every
        # table in this script owns its own identity sequence that the app
        # role needs USAGE on to INSERT -- except referral_stats, whose
        # primary key is user_id (no surrogate identity sequence exists).
        for table in EXPECTED_TABLE_GRANTS:
            if table == "referral_stats":
                continue
            sequence_name = f"{table}_id_seq"
            self.assertIn(sequence_name, self.sequence_grants, f"missing sequence grant for {table}")
            self.assertEqual(
                self.sequence_grants[sequence_name], {"stocknewsbr_app", "stocknewsbr_worker"}
            )

    def test_no_broad_or_dangerous_grants(self):
        upper_sql = self.sql.upper()
        self.assertNotIn("GRANT ALL", upper_sql)
        self.assertNotIn("BYPASSRLS", upper_sql)
        self.assertNotIn("SUPERUSER", upper_sql)
        self.assertNotIn("ON ALL TABLES IN SCHEMA", upper_sql)
        self.assertNotIn("ON ALL SEQUENCES IN SCHEMA", upper_sql)
        self.assertNotIn("TO PUBLIC", upper_sql)

    def test_no_ddl_no_policy_no_credentials(self):
        upper_sql = self.sql.upper()
        for forbidden in (
            "CREATE ROLE",
            "ALTER ROLE",
            "CREATE POLICY",
            "ROW LEVEL SECURITY",
            "DROP ",
            "PASSWORD",
        ):
            self.assertNotIn(forbidden, upper_sql)
        self.assertNotIn("://", self.sql)

    def test_no_update_or_delete_grants_on_append_only_audit_tables(self):
        # Audit trails must stay insert/select only, matching Mission 36's
        # own treatment of similar audit-shaped tables.
        for table in ("auth_audit_events", "subscription_audit_logs"):
            verbs, _roles = self.table_grants[table]
            self.assertNotIn("UPDATE", verbs)
            self.assertNotIn("DELETE", verbs)


if __name__ == "__main__":
    unittest.main()

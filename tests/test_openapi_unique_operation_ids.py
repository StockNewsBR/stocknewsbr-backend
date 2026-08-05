"""P3-A regression guard: every OpenAPI operationId must be unique and the
canonical + legacy health routes must keep their HTTP contracts.

The H10 release hardening mission found a FastAPI `Duplicate Operation ID`
warning caused by two route handlers sharing the same Python function name
(`system_health`) across two routers. FastAPI derives a default operation_id
from `<function_name>_<function_name>_<method>` and the collision produced
`system_health_system_health_get` for both `/system/health` and `/system-health`.

Resolution policy (preserves the public HTTP contract):
- `/system/health`  (routes_system.py)  -> canonical protected aggregate health
  under `X-Internal-Token` (`require_internal_token`).
- `/system-health`  (api_market_routes.py) -> legacy lightweight health under
  `require_channel_access("app")`. Now carries an explicit
  `operation_id="system_health_legacy_market"` so the operationId namespace is
  unique while the path, method, payload and auth stay unchanged.

This test guards against regressions by generating the OpenAPI schema and
asserting:
1.  No FastAPI `Duplicate Operation ID` warning during `app.openapi()`.
2.  Every operationId is unique (with actionable failure listing).
3.  Both `/system/health` and `/system-health` exist in the OpenAPI paths.
4.  Both endpoints expose GET only (methods preserved).
5.  `/ping` also exists (public liveness contract from P3-B).
"""

import collections
import unittest
import warnings


def _collect_openapi():
    from app.main import app

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        openapi = app.openapi()

    ops = []
    for path, methods in openapi["paths"].items():
        for method, op in methods.items():
            ops.append(
                {
                    "operation_id": op.get("operationId"),
                    "path": path,
                    "method": method,
                }
            )

    duplicate_warnings = [
        str(w.message)
        for w in captured
        if "Duplicate Operation ID" in str(w.message)
    ]

    return openapi, ops, duplicate_warnings


class OpenApiUniqueOperationIdsTests(unittest.TestCase):
    def test_health_routes_preserved_and_unique_operation_ids(self):
        openapi, ops, duplicate_warnings = _collect_openapi()

        # 1. No FastAPI Duplicate Operation ID warning during OpenAPI gen.
        self.assertEqual(
            duplicate_warnings,
            [],
            "FastAPI emitted Duplicate Operation ID warnings during OpenAPI "
            "generation: " + " | ".join(duplicate_warnings),
        )

        # 2. All operationIds must be unique.
        counts = collections.Counter(op["operation_id"] for op in ops)
        dups = {oid: cnt for oid, cnt in counts.items() if cnt > 1}
        self.assertEqual(
            dups,
            {},
            "Duplicate operationIds found: "
            + ", ".join(
                f"{oid} (x{cnt}) at "
                + ", ".join(
                    f"{op['method'].upper()} {op['path']}"
                    for op in ops
                    if op["operation_id"] == oid
                )
                for oid, cnt in dups.items()
            ),
        )

        self.assertGreater(
            len(ops),
            0,
            "OpenAPI schema has no operations; app likely failed to bootstrap.",
        )

        paths = set(openapi["paths"].keys())

        # 3. Both health routes must exist (canonical + legacy).
        self.assertIn(
            "/system/health",
            paths,
            "Canonical protected /system/health must remain in OpenAPI.",
        )
        self.assertIn(
            "/system-health",
            paths,
            "Legacy /system-health contract must remain in OpenAPI "
            "(path preserved per H10.1 compliance fix).",
        )

        # 4. /ping public liveness must remain.
        self.assertIn(
            "/ping",
            paths,
            "Public liveness /ping must remain in OpenAPI.",
        )

        # 5. Methods preserved: GET only on both health routes.
        for path in ("/system/health", "/system-health", "/ping"):
            methods = set(openapi["paths"][path].keys())
            self.assertEqual(
                methods,
                {"get"},
                f"HTTP method contract changed for {path}: {sorted(methods)}",
            )

        # 6. operationIds for the two health routes are distinct.
        canonical_oid = openapi["paths"]["/system/health"]["get"].get("operationId")
        legacy_oid = openapi["paths"]["/system-health"]["get"].get("operationId")
        self.assertIsNotNone(canonical_oid, "/system/health has no operationId")
        self.assertIsNotNone(legacy_oid, "/system-health has no operationId")
        self.assertNotEqual(
            canonical_oid,
            legacy_oid,
            "Canonical and legacy health routes share operationId: "
            f"{canonical_oid}",
        )


if __name__ == "__main__":
    unittest.main()

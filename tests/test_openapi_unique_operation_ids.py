"""P3-A regression guard: every OpenAPI operationId must be unique.

The H10 release hardening mission found a FastAPI `Duplicate Operation ID`
warning caused by two route handlers sharing the same Python function name
(`system_health`) across two routers. FastAPI derives a default operation_id
from `<function_name>_<function_name>_<method>` and the collision produced
`system_health_system_health_get` for both `/system/health` and `/system-health`.

This test guards against regressions by generating the OpenAPI schema and
asserting every operationId is unique, reporting the offending pairs so the
failure message is actionable.
"""

import collections
import unittest
import warnings


def _collect_operations():
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

    return ops, duplicate_warnings


class OpenApiUniqueOperationIdsTests(unittest.TestCase):
    def test_all_openapi_operation_ids_are_unique(self):
        ops, duplicate_warnings = _collect_operations()

        self.assertEqual(
            duplicate_warnings,
            [],
            "FastAPI emitted Duplicate Operation ID warnings during OpenAPI "
            "generation: " + " | ".join(duplicate_warnings),
        )

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


if __name__ == "__main__":
    unittest.main()

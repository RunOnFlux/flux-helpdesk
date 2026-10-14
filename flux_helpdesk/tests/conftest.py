"""Lets the pure tests run with plain pytest, outside a bench.

Inside a bench the real frappe is importable and nothing here applies.
"""

import sys
import types

try:
    import frappe  # noqa: F401
except ImportError:
    stub = types.ModuleType("frappe")
    stub.flags = types.SimpleNamespace()
    stub._ = lambda text: text
    stub.whitelist = lambda *args, **kwargs: lambda fn: fn

    rate_limiter = types.ModuleType("frappe.rate_limiter")
    rate_limiter.rate_limit = lambda *args, **kwargs: lambda fn: fn

    utils = types.ModuleType("frappe.utils")
    utils.get_system_timezone = lambda: "UTC"

    stub.rate_limiter = rate_limiter
    stub.utils = utils
    sys.modules.update({"frappe": stub, "frappe.rate_limiter": rate_limiter, "frappe.utils": utils})

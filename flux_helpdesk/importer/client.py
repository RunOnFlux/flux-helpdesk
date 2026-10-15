"""A small Freshdesk API v2 client: paging, rate limits, nothing else.

The API key is used for basic auth and never logged.
"""

import time
from collections.abc import Iterator

import requests


class FreshdeskError(Exception):
    pass


class FreshdeskClient:
    def __init__(self, domain: str, api_key: str, session: requests.Session | None = None):
        domain = domain.strip().removeprefix("https://").rstrip("/")
        if not domain.endswith(".freshdesk.com"):
            # The portal domain (e.g. support.runonflux.io) does not answer the API.
            raise FreshdeskError("Use the account domain, e.g. yourcompany.freshdesk.com")
        self.base = f"https://{domain}/api/v2"
        self.session = session or requests.Session()
        self.session.auth = (api_key, "X")
        self.session.headers["Accept"] = "application/json"
        self.calls = 0

    def get(self, path: str, params: dict | None = None):
        for _attempt in range(6):
            self.calls += 1
            response = self.session.get(f"{self.base}{path}", params=params, timeout=60)
            if response.status_code == 429:
                time.sleep(int(response.headers.get("Retry-After", "30")) + 1)
                continue
            if response.status_code >= 500:
                time.sleep(5)
                continue
            if response.status_code == 404:
                return None
            if not response.ok:
                raise FreshdeskError(f"GET {path} answered HTTP {response.status_code}")
            return response.json()
        raise FreshdeskError(f"GET {path} kept failing")

    def paged(self, path: str, params: dict | None = None, per_page: int = 100) -> Iterator[dict]:
        page = 1
        while True:
            batch = self.get(path, {**(params or {}), "per_page": per_page, "page": page})
            if not batch:
                return
            yield from batch
            if len(batch) < per_page:
                return
            page += 1

    # Resources ----------------------------------------------------------

    def tickets(self, updated_since: str = "2000-01-01T00:00:00Z") -> Iterator[dict]:
        # Without updated_since Freshdesk only lists the last 30 days.
        return self.paged(
            "/tickets",
            {
                "updated_since": updated_since,
                "order_by": "created_at",
                "order_type": "asc",
                "include": "description,stats",
            },
        )

    def newest_ticket_id(self) -> int:
        newest = self.get(
            "/tickets",
            {
                "updated_since": "2000-01-01T00:00:00Z",
                "order_by": "created_at",
                "order_type": "desc",
                "per_page": 1,
            },
        )
        return int(newest[0]["id"]) if newest else 0

    def ticket(self, ticket_id: int) -> dict | None:
        return self.get(f"/tickets/{ticket_id}")

    def conversations(self, ticket_id: int) -> Iterator[dict]:
        return self.paged(f"/tickets/{ticket_id}/conversations")

    def contact(self, contact_id: int) -> dict | None:
        return self.get(f"/contacts/{contact_id}")

    def company(self, company_id: int) -> dict | None:
        return self.get(f"/companies/{company_id}")

    def agents(self) -> Iterator[dict]:
        return self.paged("/agents")

    def groups(self) -> Iterator[dict]:
        return self.paged("/groups")

    def solution_categories(self) -> list[dict]:
        return self.get("/solutions/categories") or []

    def solution_folders(self, category_id: int) -> list[dict]:
        return self.get(f"/solutions/categories/{category_id}/folders") or []

    def solution_articles(self, folder_id: int) -> Iterator[dict]:
        return self.paged(f"/solutions/folders/{folder_id}/articles")

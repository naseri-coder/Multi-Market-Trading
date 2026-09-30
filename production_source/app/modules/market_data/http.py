"""Shared public-REST HTTP client."""

import httpx

class AsyncJsonHttpClient:
    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout_seconds,
            transport=transport,
            headers={"Accept": "application/json"},
        )

    async def get_json(self, path: str, *, params: dict[str, object]) -> object:
        response = await self._client.get(path, params=params)
        response.raise_for_status()
        return response.json()

    async def aclose(self) -> None:
        await self._client.aclose()

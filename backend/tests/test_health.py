from httpx import ASGITransport, AsyncClient

from macedon.main import create_app


async def test_health() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_cors_allows_the_frontend_origin_only() -> None:
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        allowed = await client.options(
            "/documents",
            headers={"Origin": "http://localhost:4200", "Access-Control-Request-Method": "GET"},
        )
        denied = await client.options(
            "/documents",
            headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"},
        )

    assert allowed.headers["access-control-allow-origin"] == "http://localhost:4200"
    assert "access-control-allow-origin" not in denied.headers

from datetime import date, datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import summaries
from app.database import Base, get_db
from app.main import app
from app.models import GeneratedSummary, SummaryRequest, User
from app.services.security import create_access_token, hash_password


@pytest.fixture
async def db_factory(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/test.db", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async def override_db():
        async with factory() as session:
            yield session
    app.dependency_overrides[get_db] = override_db
    summaries.async_session_factory = factory
    yield factory
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.fixture
async def auth_headers(db_factory):
    async with db_factory() as db:
        user = User(email="u@example.com", name="User", password_hash=hash_password("password123"))
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.mark.asyncio
async def test_unauthorized_returns_401(db_factory):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/work-summaries", json={"date": "2026-07-18"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_summary_returns_job_id(db_factory, auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/work-summaries", headers=auth_headers, json={"date": "2026-07-18"})
    assert response.status_code == 202
    assert response.json()["job_id"]


@pytest.mark.asyncio
async def test_same_date_returns_cached(db_factory, auth_headers):
    async with db_factory() as db:
        user = await db.scalar(__import__("sqlalchemy").select(User).where(User.email == "u@example.com"))
        request = SummaryRequest(user_id=user.id, date=date(2026, 7, 19), timezone="Asia/Seoul", source_options={}, summary_options={}, privacy_options={}, collector_options={}, created_at=datetime.now(timezone.utc))
        db.add(request)
        await db.flush()
        summary = GeneratedSummary(request_id=request.id, user_id=user.id, content={"completed": ["done"]}, source_status={}, model="test", prompt_version="v1", chunked=False, created_at=datetime.now(timezone.utc))
        db.add(summary)
        await db.commit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/work-summaries", headers=auth_headers, json={"date": "2026-07-19"})
    assert response.status_code == 200
    assert response.json()["cached"] is True

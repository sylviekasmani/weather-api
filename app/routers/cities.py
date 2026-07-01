import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import City
from app.schemas import CityCreate, CityOut

router = APIRouter(prefix="/cities", tags=["cities"])


@router.get("", response_model=list[CityOut])
async def list_cities(
    country_code: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[City]:
    stmt = select(City).order_by(City.name)
    if country_code:
        stmt = stmt.where(City.country_code == country_code.upper())
    result = await session.execute(stmt)
    return list(result.scalars())


@router.get("/{city_id}", response_model=CityOut)
async def get_city(city_id: int, session: AsyncSession = Depends(get_session)) -> City:
    city = await session.get(City, city_id)
    if city is None:
        raise HTTPException(status_code=404, detail="City not found")
    return city


@router.post("", response_model=CityOut, status_code=201)
async def create_city(request: Request, payload: CityCreate, session: AsyncSession = Depends(get_session)) -> City:
    city = City(**payload.model_dump(), created_at=datetime.datetime.now(datetime.timezone.utc))
    session.add(city)
    await session.commit()
    await session.refresh(city)
    return city

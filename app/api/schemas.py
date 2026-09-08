from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.car import CarStatus


class CarCreate(BaseModel):
    model: str = Field(..., min_length=1, max_length=120, examples=["Tesla Model 3"])
    year: int = Field(..., ge=1950, le=2100, examples=[2023])

    model_config = ConfigDict(protected_namespaces=())


class CarUpdate(BaseModel):
    model: str | None = Field(None, min_length=1, max_length=120)
    year: int | None = Field(None, ge=1950, le=2100)
    status: CarStatus | None = None

    model_config = ConfigDict(protected_namespaces=())

    @model_validator(mode="after")
    def at_least_one_field(self):
        if self.model is None and self.year is None and self.status is None:
            raise ValueError("Provide at least one field to update")
        return self


class CarOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: int
    model: str
    year: int
    status: CarStatus
    created_at: datetime
    updated_at: datetime


class RentalCreate(BaseModel):
    car_id: int = Field(..., ge=1)
    customer_name: str = Field(..., min_length=1, max_length=120)
    start_date: date | None = None


class RentalEnd(BaseModel):
    end_date: date | None = None


class RentalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    car_id: int
    customer_name: str
    start_date: date
    end_date: date | None
    created_at: datetime


class ErrorResponse(BaseModel):
    detail: str
    code: str

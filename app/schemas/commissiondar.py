from datetime import date
from decimal import Decimal
from pydantic import BaseModel, Field


class CommissiondarFarmerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    village: str | None = Field(default=None, max_length=150)
    phone: str | None = Field(default=None, max_length=20)


class CommissiondarMillCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class CommissiondarMillUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    is_active: bool | None = None


class CommissiondarMillCommissionCreate(BaseModel):
    commission_amount: Decimal = Field(gt=0)
    earned_at: date | None = None
    note: str | None = None


class CommissiondarMillCommissionReceiptCreate(BaseModel):
    amount: Decimal = Field(gt=0)
    received_at: date | None = None
    note: str | None = None


class GrainTypeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    unit: str = Field(default="quintal", min_length=1, max_length=30)


class LoanCreate(BaseModel):
    farmer_id: int
    principal: float = Field(gt=0)
    interest_rate_pa: float = Field(default=0, ge=0)


class RepaymentCreate(BaseModel):
    loan_id: int
    amount: float = Field(gt=0)


class CommissiondarReceive(BaseModel):
    farmer_id: int
    item_id: int | None = None
    grain_type_id: int | None = None
    quantity: float = Field(gt=0)
    rate: float | None = Field(default=None, gt=0)


class CommissiondarDeliver(BaseModel):
    farmer_id: int
    mill_name: str = Field(min_length=1, max_length=200)
    item_id: int | None = None
    grain_type_id: int | None = None
    quantity: float = Field(gt=0)
    rate: float | None = Field(default=None, gt=0)

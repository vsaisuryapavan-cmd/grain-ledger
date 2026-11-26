from pydantic import BaseModel, Field


class FarmerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    village: str = Field(min_length=1, max_length=150)
    associated_commissiondar_id: int | None = None


class FarmerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    village: str | None = Field(default=None, min_length=1, max_length=150)
    associated_commissiondar_id: int | None = None


class CommissiondarContactCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    phone: str | None = Field(default=None, max_length=20)
    village: str | None = Field(default=None, max_length=150)


class CommissiondarContactUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    phone: str | None = Field(default=None, max_length=20)
    village: str | None = Field(default=None, max_length=150)
    is_active: bool | None = None


class ItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=100)
    unit: str = Field(min_length=1, max_length=50)


class ItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=100)
    unit: str | None = Field(default=None, min_length=1, max_length=50)


class IntakeCreate(BaseModel):
    farmer_id: int
    item_id: int
    quantity: float = Field(gt=0)
    rate: float = Field(gt=0)
    moisture_pct: float | None = Field(default=None, ge=0, le=100)
    broker_id: int | None = None
    # Legacy total commission remains supported for old clients.
    commission_amount: float | None = Field(default=None, ge=0)
    packet_count: int | None = Field(default=None, gt=0)
    packet_price: float | None = Field(default=None, gt=0)
    commission_type: str | None = Field(default=None, pattern="^(fixed|percentage)$")
    commission_rate: float | None = Field(default=None, ge=0)


class PaymentCreate(BaseModel):
    farmer_id: int
    amount: float = Field(gt=0)
    mode: str | None = None


class MillLoanCreate(BaseModel):
    commissiondar_id: int
    principal: float = Field(gt=0)
    interest_rate_pa: float = Field(default=0, ge=0)


class MillRepaymentCreate(BaseModel):
    loan_id: int
    amount: float = Field(gt=0)


class ExportCreate(BaseModel):
    buyer_id: int
    item_id: int
    quantity: float = Field(gt=0)
    rate: float = Field(gt=0)


class CommissionPay(BaseModel):
    commission_id: int

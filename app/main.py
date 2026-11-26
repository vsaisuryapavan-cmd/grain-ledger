from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import CORS_ORIGINS
from app.routes import (
    admin,
    auth,
    commissiondar_dashboard,
    commissiondar_farmers,
    commissiondar_loans,
    commissiondar_mills,
    commissiondar_stock,
    miller_finance,
    miller_inventory,
    miller_parties,
)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "message": "Grain Ledger API is running"
    }


app.include_router(auth.router)
app.include_router(miller_finance.router)
app.include_router(commissiondar_loans.router)
app.include_router(commissiondar_dashboard.router)
app.include_router(commissiondar_stock.router)
app.include_router(admin.router)
app.include_router(miller_parties.router)
app.include_router(commissiondar_farmers.router)
app.include_router(commissiondar_mills.router)
app.include_router(miller_inventory.router)

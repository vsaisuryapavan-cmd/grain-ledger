import sys as _sys, os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..'))


import getpass
import sys

from dotenv import load_dotenv
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

# Load the local test environment BEFORE importing database.py.
load_dotenv(".env.test", override=True)

database_url = make_url(
    __import__("os").environ["DATABASE_URL"]
)

# Safety guard: this script must never create an Admin on Render.
if database_url.host not in ("localhost", "127.0.0.1"):
    sys.exit("ERROR: Admin bootstrap is allowed only on localhost.")

if database_url.database != "grain_ledger_test":
    sys.exit("ERROR: Expected the grain_ledger_test database.")

from app.core.database import SessionLocal
from app.models import Business, User
from app.core.security import hash_password


def main():
    name = input("Admin name: ").strip()
    phone = input("Admin phone: ").strip()

    if not name or not phone:
        sys.exit("Name and phone are required.")

    if not (10 <= len(phone) <= 20):
        sys.exit("Phone must contain 10 to 20 characters.")

    password = getpass.getpass("Admin password: ")
    confirm_password = getpass.getpass("Confirm Admin password: ")

    second_password = getpass.getpass("Admin second password: ")
    confirm_second = getpass.getpass("Confirm second password: ")

    if not password or not second_password:
        sys.exit("Both passwords are required.")

    if password != confirm_password:
        sys.exit("Admin passwords do not match.")

    if second_password != confirm_second:
        sys.exit("Second passwords do not match.")

    db = SessionLocal()

    try:
        # This is a one-time bootstrap.
        if db.query(User).filter(User.role == "admin").first():
            sys.exit("An Admin already exists. Bootstrap blocked.")

        if db.query(User).filter(User.phone == phone).first():
            sys.exit("This phone number is already registered.")

        # Create the separate system business.
        business = Business(
            name="Grain Ledger Admin",
            business_type="system"
        )

        db.add(business)
        db.flush()

        # Create the approved Admin account.
        admin = User(
            business_id=business.id,
            name=name,
            phone=phone,
            role="admin",
            party_id=None,
            password_hash=hash_password(password),
            second_password_hash=hash_password(second_password),
            approval_status="approved"
        )

        db.add(admin)
        db.commit()

        print("\nAdmin account created successfully.")
        print("Admin ID:", admin.id)
        print("Business ID:", business.id)
        print("Role: admin")
        print("Approval status: approved")
        print("Passwords stored as hashes.")

    except IntegrityError:
        db.rollback()
        print("ERROR: Phone number already registered or database constraint failed.")

    except Exception:
        db.rollback()
        print("ERROR: Admin creation failed. No changes were committed.")
        raise

    finally:
        db.close()


if __name__ == "__main__":
    main()

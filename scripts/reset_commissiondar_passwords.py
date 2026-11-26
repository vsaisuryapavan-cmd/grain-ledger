import sys as _sys, os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..'))

import os
import sys

from dotenv import load_dotenv
from getpass import getpass
from sqlalchemy.engine import make_url

# Load LOCAL TEST database configuration
load_dotenv(".env.test", override=True)

database_url_value = os.environ.get("DATABASE_URL")

if not database_url_value:
    sys.exit("ERROR: DATABASE_URL is missing.")

database_url = make_url(database_url_value)

if database_url.host not in ("localhost", "127.0.0.1"):
    sys.exit("ERROR: Password reset is allowed only on localhost.")

if database_url.database != "grain_ledger_test":
    sys.exit("ERROR: Expected the grain_ledger_test database.")

from app.core.database import SessionLocal
from app.models import User
from app.core.security import hash_password

db = SessionLocal()

try:
    # Find local Commissiondar test account
    user = db.query(User).filter(
        User.phone == "8888888888"
    ).first()

    if not user:
        print("Commissiondar account not found in test database.")

    else:
        print("Commissiondar account found:", user.name)

        password1 = getpass("Enter new first password: ")
        password2 = getpass("Enter new second password: ")

        if not password1 or not password2:
            print("Error: Passwords cannot be empty.")

        elif password1 == password2:
            print("Error: Please use two different passwords.")

        else:
            user.password_hash = hash_password(password1)
            user.second_password_hash = hash_password(password2)

            db.commit()

            print("\nBoth Commissiondar passwords updated successfully!")

except Exception as e:
    db.rollback()
    print("Password reset failed:", str(e))

finally:
    db.close()

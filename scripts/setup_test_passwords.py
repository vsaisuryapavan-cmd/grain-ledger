import sys as _sys, os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..'))

from tests.test_database import TestSessionLocal
from app.models import User
from app.core.security import hash_password

db = TestSessionLocal()

try:
    test_users = {
    "9999999999": ("OwnerTest123!", "OwnerSecond123!"),
    "8888888888": ("PartyTest123!", "PartySecond123!"),
    "7093355518": ("AdminTest123!", "AdminSecond123!")
}

    for phone, passwords in test_users.items():
        user = db.query(User).filter(User.phone == phone).first()

        if not user:
            print(f"User {phone} not found")
            continue

        user.password_hash = hash_password(passwords[0])
        user.second_password_hash = hash_password(passwords[1])

    db.commit()
    print("Test passwords configured successfully")

finally:
    db.close()
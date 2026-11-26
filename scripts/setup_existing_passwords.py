
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from getpass import getpass

from app.core.database import SessionLocal, engine
from app.models import User
from app.core.security import hash_password


def main():
    # Strictly restrict this script to the local test database.
    if engine.url.host not in ("localhost", "127.0.0.1"):
        print("SAFETY STOP: Only localhost is allowed.")
        return

    if engine.url.database != "grain_ledger_test":
        print("SAFETY STOP: Database must be grain_ledger_test.")
        return

    print("Local test database confirmed.")

    db = SessionLocal()

    try:
        users = db.query(User).order_by(User.id).all()
        print(f"\nFound {len(users)} users.\n")

        for user in users:
            print(f"Account: {user.name}")
            print(f"Phone: {user.phone}")

            if user.password_hash:
                print("Password already exists. Skipping.\n")
                continue

            password = getpass("Enter password: ")

            if len(password) < 8:
                print("Password must contain at least 8 characters.")
                db.rollback()
                return

            confirm = getpass("Confirm password: ")

            if password != confirm:
                print("Passwords do not match.")
                db.rollback()
                return

            user.password_hash = hash_password(password)
            print("Password prepared.\n")

        db.commit()
        print("Password setup completed successfully.")

    except Exception:
        db.rollback()
        print("An error occurred. Changes were rolled back.")
        raise

    finally:
        db.close()


if __name__ == "__main__":
    main()

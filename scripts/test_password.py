import sys as _sys, os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..'))

from app.core.security import hash_password, verify_password

password = "Test12345"

hashed = hash_password(password)

print("Password hashed successfully!")
print("Correct password:", verify_password(password, hashed))
print("Wrong password:", verify_password("Wrong123", hashed))
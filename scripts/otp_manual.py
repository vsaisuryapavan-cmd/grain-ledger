import sys as _sys, os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..'))

from app.core.security import create_otp_challenge, verify_otp

challenge_id = create_otp_challenge(user_id=1)

print("Challenge ID:", challenge_id)

otp = input("Enter OTP from terminal: ")

result = verify_otp(challenge_id, otp)

print("OTP verification:", result)
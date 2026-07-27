from app.security import hash_password, verify_password

def test_hash_password():
    pwd = "my_secret_password"
    hashed = hash_password(pwd)
    assert hashed != pwd
    assert verify_password(pwd, hashed)

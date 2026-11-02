from app.infrastructure.secrets import protect_secret, unprotect_secret


def test_secret_round_trip_uses_fernet_compatible_token():
    token = protect_secret("测试密码-P@ssw0rd", "unit-test-secret")
    assert token.startswith("gAAAA")
    assert unprotect_secret(token, "unit-test-secret") == "测试密码-P@ssw0rd"

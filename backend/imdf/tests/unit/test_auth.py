"""认证系统单元测试"""
import pytest, sys, os
IMDF_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, IMDF_ROOT)
from api.auth_routes import AuthService

class TestAuth:
    def test_register_valid(self):
        r = AuthService.register("testuser9","Test1234!","annotator")
        assert "username" in r
    
    def test_register_duplicate(self):
        AuthService.register("dupuser","Dup1234!","annotator")
        with pytest.raises(ValueError):
            AuthService.register("dupuser","Dup1234!","annotator")
    
    def test_register_weak_password(self):
        with pytest.raises(ValueError):
            AuthService.register("u1","123","annotator")
    
    def test_login_valid(self):
        AuthService.register("loginuser","Login123!","annotator")
        r = AuthService.login("loginuser","Login123!")
        assert r.get("access_token") or r.get("token")
    
    def test_login_wrong_password(self):
        AuthService.register("wrongpw","Wrong123!","annotator")
        with pytest.raises(ValueError):
            AuthService.login("wrongpw","badpassword")
    
    def test_validate_token(self):
        AuthService.register("tokuser","Token123!","annotator")
        r = AuthService.login("tokuser","Token123!")
        token = r.get("access_token","")
        if token:
            payload = AuthService.validate_token(token)
            assert payload is not None

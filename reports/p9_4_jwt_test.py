"""P9-4 JWT security tests - written to file for proper handling."""
import sys, time, base64
sys.path.insert(0, 'backend')
from auth.unified_auth import JWTManager
import jwt as pyjwt

secret = 'test-secret-32bytes-audit-p9-4-jwt-test'
m = JWTManager(secret)

# === JWT TEST 1: 签名伪造 ===
print('=== JWT TEST 1: 伪造 token 检测 ===')
fake = pyjwt.encode({'sub':'admin','role':'admin'}, 'wrong-secret', algorithm='HS256')
result = m.verify_token(fake, 'access')
print(f'  伪造 token 验证: {result} (expected None)')
assert result is None, "FAIL: forged token should not validate"

# === JWT TEST 2: 过期 token ===
print('=== JWT TEST 2: 过期检测 ===')
expired_payload = {'sub':'u','type':'access','iat':int(time.time())-7200,'exp':int(time.time())-3600}
expired = pyjwt.encode(expired_payload, secret, algorithm='HS256')
result = m.verify_token(expired, 'access')
print(f'  过期 token 验证: {result} (expected None)')
assert result is None, "FAIL: expired token should not validate"

# === JWT TEST 3: 类型混淆 ===
print('=== JWT TEST 3: 类型混淆 ===')
access_tok = m.create_access_token('u001', 'tester', 'viewer', ['test:read'])
result = m.verify_token(access_tok, 'refresh')
print(f'  access token 当 refresh 用: {result} (expected None)')
assert result is None, "FAIL: access token should not validate as refresh"

# === JWT TEST 4: 篡改 payload ===
print('=== JWT TEST 4: 篡改检测 ===')
parts = access_tok.split('.')
payload_decoded = base64.urlsafe_b64decode(parts[1] + '==').decode()
print(f'  原 payload: {payload_decoded[:80]}')
tampered = access_tok[:-3] + 'XXX'
result = m.verify_token(tampered, 'access')
print(f'  篡改后 token 验证: {result} (expected None)')
assert result is None, "FAIL: tampered token should not validate"

# === JWT TEST 5: 正确 token ===
print('=== JWT TEST 5: 正常流程 ===')
result = m.verify_token(access_tok, 'access')
print(f'  正常 access token: sub={result.get("sub")}, role={result.get("role")}')
assert result is not None
assert result.get('sub') == 'u001'

# === JWT TEST 6: 刷新令牌工作流 ===
print('=== JWT TEST 6: 刷新令牌 ===')
refresh_tok = m.create_refresh_token('u001')
result = m.verify_token(refresh_tok, 'refresh')
print(f'  refresh token 验证: sub={result.get("sub")}')
assert result is not None
assert result.get('type') == 'refresh'

# === JWT TEST 7: 缺失签名 ===
print('=== JWT TEST 7: 无签名 token ===')
unsigned = base64.urlsafe_b64encode(b'{"sub":"admin","role":"admin","type":"access","exp":9999999999}').decode().rstrip('=')
fake_unsigned = f'{unsigned}.{unsigned}.'
result = m.verify_token(fake_unsigned, 'access')
print(f'  无签名 token 验证: {result} (expected None)')
assert result is None

print('=== ALL 7 JWT SECURITY TESTS PASS ===')

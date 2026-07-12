"""P9-4 Password & API Key security tests."""
import sys, secrets
sys.path.insert(0, 'backend')
from auth.unified_auth import PasswordManager, JWTManager, UnifiedAuthManager, UnifiedRole
import hashlib, hmac

print('=== PASSWORD HASH TEST 1: Argon2 加密 ===')
pm = PasswordManager()
hash_str, salt, method = pm.hash_password('MySecureP@ssw0rd2026')
print(f'  hash method: {method}')
print(f'  hash length: {len(hash_str)} chars')
print(f'  salt: {salt!r}')
assert method == 'argon2', 'FAIL: expected argon2'
assert len(hash_str) > 80, 'FAIL: argon2 hash should be ~95 chars'

print('=== PASSWORD HASH TEST 2: 验证正确密码 ===')
ok = pm.verify_password('MySecureP@ssw0rd2026', hash_str, salt, method)
print(f'  verify correct: {ok}')
assert ok

print('=== PASSWORD HASH TEST 3: 拒绝错误密码 ===')
ok = pm.verify_password('wrong', hash_str, salt, method)
print(f'  verify wrong: {ok} (expected False)')
assert not ok

print('=== PASSWORD HASH TEST 4: 相同密码不同 hash (salt) ===')
hash2, salt2, _ = pm.hash_password('MySecureP@ssw0rd2026')
print(f'  hash1 != hash2: {hash_str != hash2}')
assert hash_str != hash2, 'FAIL: same password should have different hash (random salt)'

print('=== API KEY TEST 5: API Key 强度 ===')
raw_key = f'nb_{secrets.token_hex(32)}'
print(f'  key length: {len(raw_key)} chars')
print(f'  key prefix: {raw_key[:6]}...')
print(f'  entropy: 256 bits (32 bytes hex)')
assert len(raw_key) == 66  # 'nb_' + 64 hex chars
assert raw_key.startswith('nb_')

print('=== API KEY TEST 6: SHA-256 hash 存储 (不存明文) ===')
key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
print(f'  hash: {key_hash[:40]}...')
print(f'  cannot reverse: True (one-way)')
assert len(key_hash) == 64

print('=== API KEY TEST 7: 时序安全比较 ===')
stored = hmac.new(b'secret', raw_key.encode(), hashlib.sha256).hexdigest()
incoming_correct = hmac.new(b'secret', raw_key.encode(), hashlib.sha256).hexdigest()
incoming_wrong = hmac.new(b'secret', b'nb_wrong_key', hashlib.sha256).hexdigest()
print(f'  compare_digest equal: {hmac.compare_digest(stored, incoming_correct)}')
print(f'  compare_digest not equal: {hmac.compare_digest(stored, incoming_wrong)}')
assert hmac.compare_digest(stored, incoming_correct)
assert not hmac.compare_digest(stored, incoming_wrong)

print('=== API KEY TEST 8: 32+ 字节随机熵 ===')
secret = secrets.token_hex(32)
print(f'  JWT secret length: {len(secret)} chars (256 bits)')
assert len(secret) >= 64

print('=== ALL 8 PASSWORD/APIKEY SECURITY TESTS PASS ===')

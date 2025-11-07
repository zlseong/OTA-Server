# PQC TLS 핸드셰이크 검증 가이드

## 🎯 검증 방법 3가지

### 1️⃣ Shell 스크립트 (자동화)
### 2️⃣ Python 도구 (상세 분석)
### 3️⃣ OpenSSL 명령어 (수동)

---

## 방법 1: Shell 스크립트 (가장 쉬움) ⭐

### 실행
```bash
cd tests
chmod +x test_handshake.sh
./test_handshake.sh
```

### 무엇을 검증하나요?
- ✅ OpenSSL PQC 지원 여부
- ✅ 인증서 생성 (ECDSA)
- ✅ ML-KEM-768 + ECDSA 핸드셰이크
- ✅ mTLS 클라이언트 인증
- ✅ Python 호환성

### 예상 출력
```
╔════════════════════════════════════════════════════════════╗
║   PQC TLS Handshake Verification (ML-KEM + ECDSA)         ║
╚════════════════════════════════════════════════════════════╝

[TEST] Step 0: Checking OpenSSL version...
OpenSSL: OpenSSL 3.6.0
[PASS] ML-KEM support detected

[TEST] Step 1: Generating test certificates...
[PASS] CA certificate created
[PASS] Server certificate created (ECDSA)
[PASS] Client certificate created (ECDSA)

[TEST] Step 2: Starting OpenSSL test server...
[PASS] Server started (PID: 12345)

[TEST] Step 3: Testing TLS handshake with s_client...
Verification: OK
[PASS] TLS handshake successful
[PASS] Protocol: TLS 1.3
Cipher: TLS_AES_128_GCM_SHA256

[TEST] Step 5: Testing with Python client...
✅ Python handshake successful
   Protocol: TLSv1.3
   Cipher: TLS_AES_128_GCM_SHA256
   Peer cert verified: True

╔════════════════════════════════════════════════════════════╗
║   Test Summary                                             ║
╚════════════════════════════════════════════════════════════╝
[PASS] All tests passed! ML-KEM + ECDSA handshake working correctly

Key Exchange: ML-KEM-768 (Post-Quantum)
Signature: ECDSA secp256r1 (Classical)
Protocol: TLS 1.3
mTLS: Client certificate verified
```

---

## 방법 2: Python 검증 도구

### 2-1. 단일 테스트
```bash
cd tests
python3 verify_handshake.py
```

**출력**:
```
Testing single handshake (ML-KEM-768 + ECDSA)...

✅ Handshake successful
   Protocol: TLSv1.3
   Cipher: TLS_AES_128_GCM_SHA256
   Time: 12.34 ms
   Peer cert verified: True
   Data transfer: OK
```

### 2-2. 종합 테스트 (30회 반복)
```bash
python3 verify_handshake.py --comprehensive
```

**출력**:
```
============================================================
PQC TLS Handshake Test - 30 runs
============================================================

[1/30] Testing handshake...
   ✅ 11.23 ms
[2/30] Testing handshake...
   ✅ 10.87 ms
...
[30/30] Testing handshake...
   ✅ 12.01 ms

============================================================
Test Summary
============================================================
Success rate: 30/30 (100.0%)
Average handshake time: 11.45 ms

Results saved to handshake_results.json
```

### 2-3. 알고리즘 조합 테스트
```bash
python3 verify_handshake.py --algorithms
```

**출력**:
```
╔════════════════════════════════════════════════════════════╗
║   PQC TLS Algorithm Combinations Test                     ║
╚════════════════════════════════════════════════════════════╝

🔐 Testing: Baseline (Classical)
   KEM: x25519, Signature: ECDSA+SHA256
✅ Handshake successful
   Protocol: TLSv1.3
   Cipher: TLS_AES_128_GCM_SHA256
   Time: 8.79 ms

🔐 Testing: ML-KEM-512 + ECDSA
   KEM: mlkem512, Signature: ECDSA+SHA256
✅ Handshake successful
   Time: 9.23 ms

🔐 Testing: ML-KEM-768 + ECDSA (Recommended)
   KEM: mlkem768, Signature: ECDSA+SHA256
✅ Handshake successful
   Time: 10.45 ms

🔐 Testing: ML-KEM-1024 + ECDSA
   KEM: mlkem1024, Signature: ECDSA+SHA256
✅ Handshake successful
   Time: 10.89 ms
```

### 2-4. 상세 분석
```bash
python3 analyze_handshake.py
```

**출력**:
```
╔════════════════════════════════════════════════════════════╗
║        PQC TLS Handshake Analyzer                         ║
╚════════════════════════════════════════════════════════════╝

==================================================================
TLS Handshake Analysis - 2025-11-07 18:30:45
==================================================================

🔗 Connected to localhost:4433

✅ TLS Handshake completed

==================================================================
Connection Information
==================================================================
Protocol Version: TLSv1.3
Cipher Suite: TLS_AES_128_GCM_SHA256
  - Protocol: TLSv1.3
  - Bits: 128

==================================================================
Server Certificate
==================================================================
Subject: {'C': 'KR', 'O': 'Test', 'CN': 'localhost'}
Issuer: {'C': 'KR', 'O': 'Test', 'CN': 'Test-CA'}
Not Before: Nov  7 09:30:45 2025 GMT
Not After: Nov  7 09:30:45 2026 GMT

==================================================================
PQC Information
==================================================================
Key Exchange: ML-KEM (Post-Quantum)
Signature: ECDSA secp256r1 (Classical)
Hybrid Mode: Yes

==================================================================
Data Transfer Test
==================================================================
✅ Data transfer successful (512 bytes received)

==================================================================
Algorithm Comparison
==================================================================

Algorithm                      Type            Security
----------------------------------------------------------------------
X25519 + ECDSA                 Classical       Fast, but quantum-vulnerable
ML-KEM-512 + ECDSA             Hybrid          Post-quantum resistant KEM
ML-KEM-768 + ECDSA             Hybrid          Recommended (192-bit security)
ML-KEM-1024 + ECDSA            Hybrid          Maximum security (256-bit)
```

---

## 방법 3: OpenSSL 명령어 (수동)

### 1. 서버 시작
```bash
openssl s_server \
  -cert test_certs/server.crt \
  -key test_certs/server.key \
  -CAfile test_certs/ca.crt \
  -Verify 1 \
  -groups mlkem768:x25519 \
  -sigalgs ECDSA+SHA256 \
  -tls1_3 \
  -accept 4433
```

### 2. 클라이언트 연결 (다른 터미널)
```bash
openssl s_client \
  -connect localhost:4433 \
  -cert test_certs/client.crt \
  -key test_certs/client.key \
  -CAfile test_certs/ca.crt \
  -groups mlkem768 \
  -sigalgs ECDSA+SHA256 \
  -tls1_3 \
  -brief
```

### 예상 출력
```
CONNECTION ESTABLISHED
Protocol version: TLSv1.3
Ciphersuite: TLS_AES_128_GCM_SHA256
Peer certificate: CN=localhost
Hash used: SHA256
Signature type: ECDSA
Verification: OK
Supported groups: mlkem768:x25519
Server Temp Key: mlkem768
```

---

## 🔍 핸드셰이크 검증 포인트

### ✅ 체크리스트

1. **Protocol Version**
   - ✅ `TLSv1.3` 확인
   - ❌ `TLSv1.2` 이하는 PQC 미지원

2. **Key Exchange (KEM)**
   - ✅ `mlkem768` 또는 `mlkem512/1024`
   - ℹ️ `Server Temp Key: mlkem768` 출력 확인

3. **Signature Algorithm**
   - ✅ `ECDSA+SHA256` 또는 `Dilithium`
   - ℹ️ `Signature type: ECDSA` 출력 확인

4. **Certificate Verification**
   - ✅ `Verification: OK`
   - ✅ `Peer cert verified: True`

5. **mTLS (Mutual TLS)**
   - ✅ 서버가 클라이언트 인증서 요구
   - ✅ 양쪽 모두 인증서 검증

6. **Data Transfer**
   - ✅ 핸드셰이크 후 데이터 송수신 성공

---

## 📊 성능 벤치마크

### 핸드셰이크 시간 비교
```bash
# 30회 측정
python3 verify_handshake.py --comprehensive
```

| 알고리즘 | 평균 시간 | vs Baseline |
|---------|----------|------------|
| X25519 + ECDSA | 8.79 ms | - |
| ML-KEM-512 + ECDSA | 9.23 ms | +5.0% |
| ML-KEM-768 + ECDSA | 10.45 ms | +18.9% |
| ML-KEM-1024 + ECDSA | 10.89 ms | +23.9% |

---

## 🐛 트러블슈팅

### 1. "ML-KEM not supported"
**원인**: OpenSSL 버전이 낮음

**해결**:
```bash
openssl version  # 3.6.0+ 필요
# 필요시 OpenSSL 소스 빌드
```

### 2. "Handshake failed"
**원인**: 인증서 문제

**해결**:
```bash
# 인증서 재생성
./test_handshake.sh
```

### 3. "Connection refused"
**원인**: 서버 미실행

**해결**:
```bash
# 서버가 실행 중인지 확인
netstat -an | grep 4433
```

### 4. Python SSL Error
**원인**: Python SSL 모듈이 구 OpenSSL 사용

**해결**:
```bash
# Python 재빌드 (새 OpenSSL 연결)
python3 -c "import ssl; print(ssl.OPENSSL_VERSION)"
```

---

## 🎓 핵심 정리

1. **가장 쉬운 방법**: `./test_handshake.sh` 실행
2. **상세 분석**: `python3 analyze_handshake.py`
3. **성능 측정**: `python3 verify_handshake.py --comprehensive`
4. **수동 확인**: OpenSSL `s_server` + `s_client`

모든 테스트가 ✅로 표시되면 **ML-KEM + ECDSA 핸드셰이크 성공**!




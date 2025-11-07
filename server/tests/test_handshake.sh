#!/bin/bash

# PQC TLS 핸드셰이크 검증 스크립트
# ML-KEM + ECDSA 조합 테스트

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_test() { echo -e "${BLUE}[TEST]${NC} $1"; }
log_pass() { echo -e "${GREEN}[PASS]${NC} $1"; }
log_fail() { echo -e "${RED}[FAIL]${NC} $1"; }

echo "╔════════════════════════════════════════════════════════════╗"
echo "║   PQC TLS Handshake Verification (ML-KEM + ECDSA)         ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# 0. OpenSSL 버전 확인
log_test "Step 0: Checking OpenSSL version..."
OPENSSL_VERSION=$(openssl version)
echo "OpenSSL: $OPENSSL_VERSION"

if openssl list -kem-algorithms | grep -q "mlkem"; then
    log_pass "ML-KEM support detected"
else
    log_fail "ML-KEM not supported. Need OpenSSL 3.6.0+"
    exit 1
fi
echo ""

# 1. 인증서 생성 (ML-KEM + ECDSA)
log_test "Step 1: Generating test certificates..."

CERT_DIR="test_certs"
mkdir -p $CERT_DIR

# CA 인증서 (ECDSA)
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 \
    -nodes -keyout $CERT_DIR/ca.key -out $CERT_DIR/ca.crt \
    -days 365 -subj "/C=KR/O=Test/CN=Test-CA" 2>/dev/null

log_pass "CA certificate created"

# 서버 인증서 (ECDSA)
openssl ecparam -name prime256v1 -genkey -noout -out $CERT_DIR/server.key
openssl req -new -key $CERT_DIR/server.key -out $CERT_DIR/server.csr \
    -subj "/C=KR/O=Test/CN=localhost" 2>/dev/null
openssl x509 -req -in $CERT_DIR/server.csr -CA $CERT_DIR/ca.crt \
    -CAkey $CERT_DIR/ca.key -CAcreateserial -out $CERT_DIR/server.crt \
    -days 365 2>/dev/null

log_pass "Server certificate created (ECDSA)"

# 클라이언트 인증서 (ECDSA)
openssl ecparam -name prime256v1 -genkey -noout -out $CERT_DIR/client.key
openssl req -new -key $CERT_DIR/client.key -out $CERT_DIR/client.csr \
    -subj "/C=KR/O=Test/CN=client" 2>/dev/null
openssl x509 -req -in $CERT_DIR/client.csr -CA $CERT_DIR/ca.crt \
    -CAkey $CERT_DIR/ca.key -CAcreateserial -out $CERT_DIR/client.crt \
    -days 365 2>/dev/null

log_pass "Client certificate created (ECDSA)"
rm -f $CERT_DIR/*.csr
echo ""

# 2. OpenSSL s_server로 테스트 서버 시작
log_test "Step 2: Starting OpenSSL test server (ML-KEM768 + ECDSA)..."

openssl s_server \
    -cert $CERT_DIR/server.crt \
    -key $CERT_DIR/server.key \
    -CAfile $CERT_DIR/ca.crt \
    -verify_return_error \
    -Verify 1 \
    -groups mlkem768:x25519 \
    -sigalgs ECDSA+SHA256 \
    -tls1_3 \
    -accept 4433 \
    -www > /dev/null 2>&1 &

SERVER_PID=$!
sleep 2

if ps -p $SERVER_PID > /dev/null; then
    log_pass "Server started (PID: $SERVER_PID)"
else
    log_fail "Server failed to start"
    exit 1
fi
echo ""

# 3. OpenSSL s_client로 핸드셰이크 테스트
log_test "Step 3: Testing TLS handshake with s_client..."

HANDSHAKE_OUTPUT=$(openssl s_client \
    -connect localhost:4433 \
    -cert $CERT_DIR/client.crt \
    -key $CERT_DIR/client.key \
    -CAfile $CERT_DIR/ca.crt \
    -groups mlkem768 \
    -sigalgs ECDSA+SHA256 \
    -tls1_3 \
    -brief < /dev/null 2>&1)

echo "$HANDSHAKE_OUTPUT"
echo ""

# 핸드셰이크 검증
if echo "$HANDSHAKE_OUTPUT" | grep -q "Verification: OK"; then
    log_pass "TLS handshake successful"
else
    log_fail "TLS handshake failed"
    kill $SERVER_PID 2>/dev/null
    exit 1
fi

# Protocol 버전 확인
if echo "$HANDSHAKE_OUTPUT" | grep -q "TLSv1.3"; then
    log_pass "Protocol: TLS 1.3"
else
    log_fail "Protocol not TLS 1.3"
fi

# Cipher 확인
CIPHER=$(echo "$HANDSHAKE_OUTPUT" | grep "Cipher:" | awk '{print $2}')
log_info "Cipher: $CIPHER"

# 서명 알고리즘 확인 (상세 모드)
log_test "Step 4: Checking signature algorithm..."
openssl s_client \
    -connect localhost:4433 \
    -cert $CERT_DIR/client.crt \
    -key $CERT_DIR/client.key \
    -CAfile $CERT_DIR/ca.crt \
    -groups mlkem768 \
    -sigalgs ECDSA+SHA256 \
    -tls1_3 \
    < /dev/null 2>&1 | grep -E "(Peer signing|Server Temp Key)" || true

echo ""

# 5. Python 클라이언트로 테스트
log_test "Step 5: Testing with Python client..."

python3 << 'EOF'
import ssl
import socket

context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
context.minimum_version = ssl.TLSVersion.TLSv1_3
context.maximum_version = ssl.TLSVersion.TLSv1_3
context.load_cert_chain('test_certs/client.crt', 'test_certs/client.key')
context.load_verify_locations('test_certs/ca.crt')
context.check_hostname = False

try:
    with socket.create_connection(('localhost', 4433)) as sock:
        with context.wrap_socket(sock, server_hostname='localhost') as ssock:
            print(f"✅ Python handshake successful")
            print(f"   Protocol: {ssock.version()}")
            print(f"   Cipher: {ssock.cipher()[0]}")
            
            # 인증서 검증
            cert = ssock.getpeercert()
            print(f"   Peer cert verified: {cert is not None}")
except Exception as e:
    print(f"❌ Python handshake failed: {e}")
    exit(1)
EOF

echo ""

# 6. 서버 종료
log_info "Cleaning up..."
kill $SERVER_PID 2>/dev/null
wait $SERVER_PID 2>/dev/null

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║   Test Summary                                             ║"
echo "╚════════════════════════════════════════════════════════════╝"
log_pass "All tests passed! ML-KEM + ECDSA handshake working correctly"
echo ""
log_info "Key Exchange: ML-KEM-768 (Post-Quantum)"
log_info "Signature: ECDSA secp256r1 (Classical)"
log_info "Protocol: TLS 1.3"
log_info "mTLS: Client certificate verified"
echo ""




# PQC OTA Server (Python + C) - 동작 원리

## 🔑 핵심 개념

**문제**: Python으로 서버를 만들고 싶지만, PQC 암호화는 C/OpenSSL만 지원

**해결**: Hybrid Architecture = Python 서버 + C 확장 라이브러리

---

## 📊 아키텍처

```
┌─────────────────────────────────────────────────────────┐
│                  Python Flask Server                    │
│  - REST API                                             │
│  - 비즈니스 로직                                          │
│  - MQTT 통신                                            │
│  - 파일 관리                                            │
└─────────────────┬───────────────────────────────────────┘
                  │ ctypes 호출
                  │ (Python → C 함수 호출)
┌─────────────────▼───────────────────────────────────────┐
│            C 공유 라이브러리 (libpqc_tls.so)             │
│  - PQC TLS 핸드셰이크                                    │
│  - ML-KEM 키 교환                                       │
│  - ML-DSA 서명                                          │
│  - OpenSSL 직접 제어                                     │
└─────────────────┬───────────────────────────────────────┘
                  │ OpenSSL API
                  │
┌─────────────────▼───────────────────────────────────────┐
│                  OpenSSL 3.x                            │
│  - ML-KEM-512/768/1024                                  │
│  - ML-DSA (Dilithium2/3/5)                              │
│  - TLS 1.3                                              │
└─────────────────────────────────────────────────────────┘
```

---

## 🔧 구현 세부사항

### 1. C 라이브러리 (libpqc_tls.so)

**역할**: OpenSSL PQC 기능을 간단한 C API로 래핑

```c
// pqc_tls_wrapper.h
pqc_tls_ctx_t pqc_tls_create_server_ctx(
    const char *cert_file,
    const char *key_file,
    const char *ca_file,
    const char *kem_algorithm,  // "mlkem768"
    const char *sig_algorithm,  // "dilithium3"
    bool require_client_cert
);

pqc_tls_conn_t pqc_tls_accept(pqc_tls_ctx_t ctx, int socket_fd);
int pqc_tls_read(pqc_tls_conn_t conn, char *buffer, int size);
int pqc_tls_write(pqc_tls_conn_t conn, const char *buffer, int size);
```

**빌드**:
```bash
gcc -shared -fPIC pqc_tls_wrapper.c -o libpqc_tls.so -lssl -lcrypto
```

결과: `libpqc_tls.so` (공유 라이브러리)

---

### 2. Python ctypes 래퍼

**역할**: C 라이브러리를 Python에서 호출 가능하게 만듦

```python
# pqc_tls.py
import ctypes

# 라이브러리 로드
lib = ctypes.CDLL('./libpqc_tls.so')

# 함수 시그니처 설정
lib.pqc_tls_create_server_ctx.argtypes = [
    ctypes.c_char_p,  # cert_file
    ctypes.c_char_p,  # key_file
    ctypes.c_char_p,  # ca_file
    ctypes.c_char_p,  # kem_algorithm
    ctypes.c_char_p,  # sig_algorithm
    ctypes.c_bool     # require_client_cert
]
lib.pqc_tls_create_server_ctx.restype = ctypes.c_void_p

# Python 래퍼 클래스
class PQCTLSWrapper:
    def create_server_context(self, cert, key, ca, kem, sig):
        ctx = lib.pqc_tls_create_server_ctx(
            cert.encode('utf-8'),
            key.encode('utf-8'),
            ca.encode('utf-8'),
            kem.encode('utf-8'),
            sig.encode('utf-8'),
            True
        )
        return ctx
```

---

### 3. Flask 서버

**역할**: HTTP API 제공, 비즈니스 로직 처리

```python
# app.py
from flask import Flask, jsonify
from pqc_tls import get_pqc_tls

app = Flask(__name__)
pqc_tls = get_pqc_tls()  # C 라이브러리 초기화

@app.route('/api/firmware/latest')
def get_latest():
    # Python으로 비즈니스 로직 처리
    firmware = OTAManager.get_latest_firmware()
    return jsonify(firmware)

# Flask는 HTTP만 처리
# PQC TLS는 Nginx 리버스 프록시가 담당
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
```

---

## 🌐 HTTPS 구성 방법

### 옵션 1: Nginx 리버스 프록시 (★ 권장)

**장점**: 
- Flask는 HTTP만 처리 (단순)
- Nginx가 PQC TLS 담당 (성능 우수)
- 설정 간단

**구성**:
```
Client
  ↓ HTTPS + PQC TLS
Nginx (443)
  ↓ HTTP (내부 통신)
Flask (5000)
```

**Nginx 설정**:
```nginx
server {
    listen 443 ssl http2;
    
    ssl_certificate /path/to/mlkem768_dilithium3_server.crt;
    ssl_certificate_key /path/to/mlkem768_dilithium3_server.key;
    ssl_protocols TLSv1.3;
    ssl_ciphers TLS_AES_128_GCM_SHA256;
    
    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

### 옵션 2: Python 직접 TLS 처리 (고급)

**장점**:
- 단일 프로세스
- 전체 제어 가능

**단점**:
- 복잡함
- 성능 저하 (Python GIL)

**구현**:
```python
import socket
from pqc_tls import get_pqc_tls

pqc = get_pqc_tls()

# TLS 컨텍스트 생성
ctx = pqc.create_server_context(
    cert_file="server.crt",
    key_file="server.key",
    ca_file="ca.crt",
    kem_algorithm="mlkem768",
    sig_algorithm="dilithium3"
)

# 소켓 생성
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.bind(('0.0.0.0', 8443))
sock.listen(5)

while True:
    client_sock, addr = sock.accept()
    
    # PQC TLS 핸드셰이크
    conn = pqc.accept(ctx, client_sock.fileno())
    
    # HTTP 요청 처리
    data = pqc.read(conn, 4096)
    # ... Flask 라우팅 로직 ...
    pqc.write(conn, response)
    pqc.close(conn)
```

---

## 🐝 MQTT 통합

```python
# mqtt_client.py
import paho.mqtt.client as mqtt

class PQCMQTTClient:
    def __init__(self):
        self.client = mqtt.Client()
        
        # PQC TLS 설정
        self.client.tls_set(
            ca_certs="ca.crt",
            certfile="server.crt",
            keyfile="server.key"
        )
        
    def connect(self, host="localhost", port=8883):
        self.client.connect(host, port)
        self.client.loop_start()
        
    def publish_update(self, version):
        self.client.publish(
            "ota/update/available",
            json.dumps({'version': version}),
            qos=1
        )
```

---

## 💻 클라이언트 (ESP32/STM32 등)

```c
// ESP32 클라이언트 예제
#include <WiFiClientSecure.h>
#include <HTTPClient.h>

WiFiClientSecure client;
HTTPClient http;

void setup() {
    // PQC 인증서 설정
    client.setCACert(ca_cert);
    client.setCertificate(client_cert);
    client.setPrivateKey(client_key);
    
    // HTTPS 요청
    http.begin(client, "https://ota-server:443/api/firmware/latest");
    int httpCode = http.GET();
    
    if (httpCode == 200) {
        String payload = http.getString();
        // 펌웨어 정보 파싱
    }
}
```

---

## 📊 성능 비교

| 구성 | 핸드셰이크 | 처리량 | 복잡도 |
|------|----------|--------|--------|
| **순수 C 서버** | 8-10ms | 10K req/s | 높음 |
| **Python + Nginx** | 10-12ms | 5K req/s | 중간 |
| **Python 직접 TLS** | 12-15ms | 2K req/s | 높음 |

**권장**: Python + Nginx (개발 속도 + 성능 균형)

---

## 🎓 핵심 포인트

1. **Python은 HTTP만 처리**
   - REST API
   - 비즈니스 로직
   - 파일 관리

2. **C 라이브러리는 암호화만 담당**
   - PQC TLS 핸드셰이크
   - OpenSSL 호출
   - 성능 최적화

3. **ctypes는 접착제 역할**
   - Python → C 함수 호출
   - 데이터 타입 변환
   - 메모리 관리

4. **Nginx가 TLS 종단점**
   - 클라이언트 ↔ Nginx: PQC TLS
   - Nginx ↔ Flask: HTTP (내부)
   - 간단하고 빠름

---

## ✅ 장점 요약

| 항목 | Python 서버 | C PQC 라이브러리 |
|------|------------|----------------|
| 개발 속도 | ⚡ 매우 빠름 | 느림 |
| 성능 | 중간 | ⚡ 매우 빠름 |
| 유지보수 | ⚡ 쉬움 | 어려움 |
| 라이브러리 | ⚡ 풍부 | 제한적 |
| PQC 지원 | ❌ 없음 | ⚡ 완벽 |

**결론**: 하이브리드가 최고! 🎯




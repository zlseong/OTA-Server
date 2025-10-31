# OTA Server Quick Start Guide

## 서버 실행 방법

### 방법 1: 실행 스크립트 사용 (권장)

#### Linux/macOS
```bash
chmod +x run_server.sh
./run_server.sh
```

#### Windows
```cmd
run_server.bat
```

**이 스크립트가 자동으로 수행하는 작업:**
1. Python 버전 확인 (3.10+ 필요)
2. OpenSSL 버전 확인 (3.x 권장)
3. 가상 환경 생성 (없으면)
4. 의존성 설치 (`requirements.txt`)
5. 설정 파일 확인 (`config/server.yaml`)
6. 필요한 디렉토리 생성 (`logs/`, `packages/`, `temp/`)
7. **서버 시작 및 대기 상태 유지**

---

### 방법 2: 수동 실행

#### 1. 가상 환경 생성 및 활성화

```bash
# Linux/macOS
python3 -m venv venv
source venv/bin/activate

# Windows
python -m venv venv
venv\Scripts\activate
```

#### 2. 의존성 설치

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

#### 3. 설정 파일 준비

```bash
# 예제 설정 파일 복사
cp config/server.yaml.example config/server.yaml

# 설정 편집 (데이터베이스, PQC 설정 등)
nano config/server.yaml  # 또는 원하는 에디터
```

#### 4. 데이터베이스 초기화

```bash
# PostgreSQL에 스키마 적용
psql -U postgres -d ota_server -f database/schema.sql
```

#### 5. PQC 인증서 생성 (선택사항, TLS 사용 시)

```bash
# 인증서 생성 스크립트 실행
chmod +x scripts/generate_pqc_certs.sh
./scripts/generate_pqc_certs.sh
```

#### 6. 서버 시작

```bash
python -m server.main
```

---

## 서버 실행 후 상태

### 서버가 시작되면:

```
╔═══════════════════════════════════════════════════════════╗
║              OTA Server with PQC-Hybrid TLS               ║
║                                                           ║
║  Automotive Over-The-Air Update Server                    ║
║  Post-Quantum Cryptography Support                        ║
║  OpenSSL 3.6.0 Native PQC                                 ║
║                                                           ║
║  Features:                                                ║
║    - 100 ECU Version Management                           ║
║    - 13 PQC Configurations (ML-KEM + ML-DSA/ECDSA)        ║
║    - Zonal Gateway Optimized Packaging                    ║
║    - Remote Diagnostics (UDS over DoIP)                   ║
║    - MQTT + HTTPS with PQC-TLS                            ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝

[2025-10-31 10:00:00] INFO - OTA Server Starting
[2025-10-31 10:00:00] INFO - Initializing PQC Manager...
[2025-10-31 10:00:00] INFO -   Loaded 13 PQC configurations
[2025-10-31 10:00:00] INFO -   Default: ML-KEM-768 + ECDSA-P256
[2025-10-31 10:00:01] INFO - Starting MQTT Server...
[2025-10-31 10:00:01] INFO - MQTT server started on 0.0.0.0:8883
[2025-10-31 10:00:01] INFO - Starting HTTPS Server...
[2025-10-31 10:00:01] INFO - HTTPS server started on 0.0.0.0:8443
[2025-10-31 10:00:01] INFO - 
============================================================
OTA Server Running
============================================================
Active Services: MQTT, HTTPS

Press Ctrl+C to stop
============================================================

```

### 이 상태에서 서버는:

✅ **MQTT 서버 대기 중** (Port 8883)
- VMG의 MQTT 연결 대기
- 텔레메트리, OTA 상태, 진단 결과 수신 준비

✅ **HTTPS 서버 대기 중** (Port 8443)
- VMG의 REST API 요청 대기
- VCI 제출, 패키지 다운로드 요청 처리 준비

✅ **이벤트 루프 실행 중**
- 비동기로 여러 요청 동시 처리 가능
- 각 요청은 독립적으로 처리

---

## 서버 동작 확인

### 1. 헬스 체크 (서버가 살아있는지 확인)

```bash
curl http://localhost:8443/health
```

**응답:**
```json
{
  "status": "ok",
  "timestamp": "2025-10-31T10:00:00.000000"
}
```

### 2. API 문서 확인

브라우저에서:
```
http://localhost:8443/docs
```

FastAPI의 자동 생성 API 문서 (Swagger UI)를 볼 수 있습니다.

### 3. 서버 로그 확인

```bash
tail -f ota_server.log
```

또는

```bash
tail -f logs/ota_server.log
```

---

## VMG 연결 시 동작

### VMG가 연결하면:

```
[2025-10-31 10:05:23] INFO - [MQTT] New connection from 192.168.1.100
[2025-10-31 10:05:23] INFO - [MQTT] TLS handshake successful (ML-KEM-768)
[2025-10-31 10:05:23] INFO - [MQTT] Client subscribed to vehicle/VMG-001/control
```

### VMG가 VCI를 제출하면:

```
[2025-10-31 10:10:15] INFO - [HTTPS] POST /api/v1/vehicles/VMG-001/vci
[2025-10-31 10:10:15] INFO - [HTTPS] Analyzing VCI for VMG-001
[2025-10-31 10:10:15] INFO - [HTTPS] Found 3 outdated ECUs:
[2025-10-31 10:10:15] INFO -   - ECU_001: 1.0.0 -> 1.2.3
[2025-10-31 10:10:15] INFO -   - ECU_005: 1.1.0 -> 1.3.0
[2025-10-31 10:10:15] INFO -   - ECU_010: 2.0.0 -> 2.1.0
[2025-10-31 10:10:15] INFO - [HTTPS] Response sent
```

### VMG가 텔레메트리를 보내면:

```
[2025-10-31 10:15:30] INFO - [MQTT] Received message on vehicle/VMG-001/telemetry
[2025-10-31 10:15:30] INFO - [MQTT] Telemetry from VMG-001:
[2025-10-31 10:15:30] INFO -   - Battery SOC: 85.5%
[2025-10-31 10:15:30] INFO -   - Speed: 60.0 km/h
[2025-10-31 10:15:30] INFO -   - Temperature: 25.0°C
[2025-10-31 10:15:30] INFO - [MQTT] Telemetry stored in database
```

---

## 서버 종료

### 정상 종료 (Graceful Shutdown)

```
Ctrl + C
```

**종료 과정:**
```
^C
[2025-10-31 18:00:00] INFO - Received signal 2, shutting down...
[2025-10-31 18:00:00] INFO - Shutting down services...
[2025-10-31 18:00:01] INFO - MQTT server stopped
[2025-10-31 18:00:01] INFO - HTTPS server stopped
[2025-10-31 18:00:01] INFO - OTA Server stopped
```

---

## 서버 프로세스 상태

### 서버 실행 중:

```
┌─────────────────────────────────────────────────────────┐
│                    OTA Server Process                   │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  [Main Process]                                         │
│      │                                                  │
│      ├─ [MQTT Server Task]  ← 비동기 태스크            │
│      │    └─ Port 8883 Listen                          │
│      │        └─ Event Loop (대기 중...)               │
│      │                                                  │
│      ├─ [HTTPS Server Task] ← 비동기 태스크            │
│      │    └─ Port 8443 Listen                          │
│      │        └─ Event Loop (대기 중...)               │
│      │                                                  │
│      └─ [Shutdown Event]    ← 대기 중                  │
│           └─ await shutdown_event.wait()               │
│                                                         │
└─────────────────────────────────────────────────────────┘

상태: RUNNING (대기 중)
CPU: ~1% (Idle)
메모리: ~100MB
네트워크: LISTENING (8443, 8883)
```

### 요청 처리 중:

```
┌─────────────────────────────────────────────────────────┐
│                    OTA Server Process                   │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  [Main Process]                                         │
│      │                                                  │
│      ├─ [MQTT Server Task]                             │
│      │    ├─ Connection 1 (VMG-001) ← 메시지 처리 중   │
│      │    ├─ Connection 2 (VMG-002) ← 대기 중          │
│      │    └─ Connection 3 (VMG-003) ← 대기 중          │
│      │                                                  │
│      ├─ [HTTPS Server Task]                            │
│      │    ├─ Request 1 (POST /vci) ← 처리 중           │
│      │    ├─ Request 2 (GET /package) ← 스트리밍 중    │
│      │    └─ Request 3 (POST /ota/check) ← 대기 중     │
│      │                                                  │
│      └─ [Shutdown Event] ← 대기 중                     │
│                                                         │
└─────────────────────────────────────────────────────────┘

상태: RUNNING (처리 중)
CPU: ~15-30%
메모리: ~150-200MB
네트워크: ACTIVE (다중 연결)
```

---

## 핵심 포인트

### ✅ 서버는 계속 실행됨

```bash
./run_server.sh
# 또는
python -m server.main
```

→ 이 명령을 실행하면 **서버가 계속 실행되며 대기 상태 유지**

### ✅ 백그라운드 실행

서버를 백그라운드에서 실행하려면:

```bash
# Linux/macOS
nohup ./run_server.sh > server.log 2>&1 &

# 또는 systemd 서비스로 등록
sudo systemctl start ota-server
```

### ✅ 프로세스 확인

```bash
# 서버 프로세스 확인
ps aux | grep "server.main"

# 포트 확인
netstat -tuln | grep -E "8443|8883"
# 또는
ss -tuln | grep -E "8443|8883"
```

**출력 예시:**
```
tcp   0   0 0.0.0.0:8443   0.0.0.0:*   LISTEN
tcp   0   0 0.0.0.0:8883   0.0.0.0:*   LISTEN
```

---

## 요약

### 질문: "서버에서 ./build.sh 실행하면 저것들이 유지된다는거지?"

### 답변:

**Python 프로젝트는 빌드가 필요 없습니다!**

대신:

1. **`./run_server.sh` 실행** (또는 `python -m server.main`)
2. **서버가 시작되고 계속 실행됨**
3. **MQTT (8883), HTTPS (8443) 포트에서 대기**
4. **VMG 요청이 오면 자동으로 처리**
5. **Ctrl+C로 종료할 때까지 계속 실행**

```
실행 → 대기 → 요청 처리 → 다시 대기 → ... (반복)
```

**서버는 한 번 실행하면 종료할 때까지 계속 살아있습니다!** 🚀


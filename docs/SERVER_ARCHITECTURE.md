# OTA Server Architecture

## 서버 구조 개요

OTA 서버는 **이벤트 기반 비동기 서버**입니다. Default 상태에서 대기하다가 VMG로부터 요청이 오면 반응합니다.

---

## 1. 서버 시작 프로세스

```
[시작]
  │
  ├─ 1. 설정 파일 로드 (config/server.yaml)
  │
  ├─ 2. PQC Manager 초기화 (13가지 PQC 설정)
  │
  ├─ 3. 데이터베이스 연결 (PostgreSQL)
  │
  ├─ 4. MQTT 서버 시작 (Port 8883, PQC-TLS)
  │     │
  │     └─ Subscribe to topics:
  │         - vehicle/+/telemetry
  │         - vehicle/+/diagnostics
  │         - vehicle/+/ota/status
  │
  ├─ 5. HTTPS 서버 시작 (Port 8443, PQC-TLS)
  │     │
  │     └─ REST API endpoints:
  │         - POST /api/v1/vehicles/register
  │         - POST /api/v1/vehicles/{vin}/vci
  │         - POST /api/v1/ota/check
  │         - GET  /api/v1/ota/package/{id}
  │         - POST /api/v1/diagnostics/send
  │
  └─ 6. 대기 상태 (Event Loop)
       │
       └─ 요청 대기 중...
```

---

## 2. 서버 동작 방식

### A. HTTPS 서버 (REST API)

```
[HTTPS Server - Port 8443]
  │
  ├─ PQC-TLS Handshake 대기
  │   │
  │   └─ VMG가 연결 시도
  │       │
  │       ├─ TLS 1.3 Handshake (ML-KEM-768 + ECDSA)
  │       ├─ mTLS 인증서 검증
  │       └─ 연결 성공
  │
  ├─ HTTP 요청 대기
  │   │
  │   └─ VMG가 요청 전송
  │       │
  │       ├─ POST /api/v1/vehicles/{vin}/vci
  │       │   └─ JSON 데이터 수신
  │       │       └─ VCI 분석
  │       │           └─ 업데이트 필요 ECU 식별
  │       │               └─ 응답 전송 (outdated_ecus)
  │       │
  │       ├─ POST /api/v1/ota/check
  │       │   └─ 버전 비교
  │       │       └─ 업데이트 가능 여부 응답
  │       │
  │       ├─ POST /api/v1/ota/package
  │       │   └─ OTA 패키지 생성
  │       │       ├─ Zonal Gateway별 그룹화
  │       │       ├─ 펌웨어 압축 (zstd)
  │       │       ├─ 패키지 서명 (PQC)
  │       │       └─ 다운로드 URL 응답
  │       │
  │       └─ GET /api/v1/ota/package/{id}
  │           └─ 파일 스트리밍 전송
  │
  └─ 다시 대기 상태로...
```

### B. MQTT 서버 (Pub/Sub)

```
[MQTT Server - Port 8883]
  │
  ├─ PQC-TLS 연결 대기
  │   │
  │   └─ VMG가 MQTT 연결
  │       │
  │       ├─ TLS Handshake
  │       ├─ MQTT CONNECT
  │       ├─ Subscribe to topics
  │       └─ 연결 유지 (Keepalive)
  │
  ├─ 메시지 대기 (Subscribe)
  │   │
  │   └─ VMG가 메시지 발행 (Publish)
  │       │
  │       ├─ Topic: vehicle/VMG-001/telemetry
  │       │   └─ JSON: { battery_soc, speed, temp, ... }
  │       │       └─ 데이터베이스 저장
  │       │           └─ 분석 (이상 감지)
  │       │
  │       ├─ Topic: vehicle/VMG-001/diagnostics
  │       │   └─ JSON: { ecu_id, service_id, response_data }
  │       │       └─ 진단 결과 저장
  │       │           └─ 대시보드 업데이트
  │       │
  │       └─ Topic: vehicle/VMG-001/ota/status
  │           └─ JSON: { update_id, status, progress }
  │               └─ OTA 상태 업데이트
  │                   └─ 진행률 추적
  │
  ├─ 메시지 발행 (Publish)
  │   │
  │   └─ 서버가 VMG로 명령 전송
  │       │
  │       ├─ Topic: vehicle/VMG-001/control
  │       │   └─ JSON: { command: "START_OTA_UPDATE", ... }
  │       │       └─ VMG가 수신
  │       │           └─ OTA 시작
  │       │
  │       └─ Topic: vehicle/VMG-001/diagnostics
  │           └─ JSON: { ecu_id, service_id: "0x22", data: "F190" }
  │               └─ VMG가 수신
  │                   └─ ZG → ECU로 전달
  │                       └─ 진단 실행
  │
  └─ 다시 대기 상태로...
```

---

## 3. 전체 시퀀스 다이어그램

### 시나리오 1: VCI 제출 및 업데이트 확인

```
VMG                          OTA Server                     Database
 │                                │                              │
 │  [1] HTTPS POST /vci           │                              │
 │─────────────────────────────>  │                              │
 │     (PQC-TLS, JSON)            │                              │
 │                                │  [2] VCI 저장                │
 │                                │─────────────────────────────>│
 │                                │                              │
 │                                │  [3] 버전 비교 쿼리          │
 │                                │─────────────────────────────>│
 │                                │<─────────────────────────────│
 │                                │     (outdated ECUs)          │
 │                                │                              │
 │  [4] Response: outdated_ecus   │                              │
 │<─────────────────────────────  │                              │
 │     { ECU_001: 1.0.0→1.2.3 }   │                              │
 │                                │                              │
 │  [5] POST /ota/package         │                              │
 │─────────────────────────────>  │                              │
 │                                │  [6] 패키지 생성             │
 │                                │  - ZG별 그룹화               │
 │                                │  - 압축 (zstd)               │
 │                                │  - 서명 (PQC)                │
 │                                │                              │
 │  [7] Response: download_url    │                              │
 │<─────────────────────────────  │                              │
 │                                │                              │
 │  [8] GET /ota/package/{id}     │                              │
 │─────────────────────────────>  │                              │
 │                                │  [9] 파일 스트리밍           │
 │<═════════════════════════════  │                              │
 │     (Binary stream)            │                              │
 │                                │                              │
```

### 시나리오 2: OTA 상태 보고 (MQTT)

```
VMG                          OTA Server                     Database
 │                                │                              │
 │  [1] MQTT Connect              │                              │
 │─────────────────────────────>  │                              │
 │     (PQC-TLS)                  │                              │
 │                                │                              │
 │  [2] Subscribe                 │                              │
 │     vehicle/VMG-001/control    │                              │
 │─────────────────────────────>  │                              │
 │                                │                              │
 │  [OTA 시작]                    │                              │
 │                                │                              │
 │  [3] Publish                   │                              │
 │     vehicle/VMG-001/ota/status │                              │
 │─────────────────────────────>  │                              │
 │     { status: "downloading",   │  [4] 상태 저장               │
 │       progress: 10% }          │─────────────────────────────>│
 │                                │                              │
 │  [5] Publish (progress)        │                              │
 │─────────────────────────────>  │  [6] 상태 업데이트           │
 │     { progress: 50% }          │─────────────────────────────>│
 │                                │                              │
 │  [7] Publish (complete)        │                              │
 │─────────────────────────────>  │  [8] 완료 처리               │
 │     { status: "completed" }    │─────────────────────────────>│
 │                                │                              │
```

### 시나리오 3: 원격 진단 (Server → VMG → ECU)

```
Admin                       OTA Server                     VMG                    ZG/ECU
 │                              │                            │                       │
 │  [1] POST /diagnostics/send  │                            │                       │
 │─────────────────────────────>│                            │                       │
 │     { ecu_id: "ECU_001",     │                            │                       │
 │       service_id: "0x22" }   │                            │                       │
 │                              │  [2] MQTT Publish          │                       │
 │                              │  vehicle/VMG-001/diagnostics                       │
 │                              │─────────────────────────────>│                       │
 │                              │                            │  [3] DoIP Forward     │
 │                              │                            │──────────────────────>│
 │                              │                            │                       │
 │                              │                            │  [4] UDS Response     │
 │                              │                            │<──────────────────────│
 │                              │  [5] MQTT Publish          │                       │
 │                              │  vehicle/VMG-001/diagnostics                       │
 │                              │<─────────────────────────────│                       │
 │                              │     { response_data }      │                       │
 │                              │                            │                       │
 │  [6] GET /diagnostics/results│                            │                       │
 │─────────────────────────────>│                            │                       │
 │<─────────────────────────────│                            │                       │
 │     { response_data }        │                            │                       │
 │                              │                            │                       │
```

---

## 4. 서버 상태 머신

```
┌─────────────────────────────────────────────────────────────┐
│                      OTA Server State                       │
└─────────────────────────────────────────────────────────────┘

[IDLE - 대기 상태]
  │
  ├─ HTTPS 요청 수신 ────────────> [PROCESSING]
  │                                     │
  │                                     ├─ VCI 분석
  │                                     ├─ 패키지 생성
  │                                     ├─ 파일 전송
  │                                     └─ 완료 ──> [IDLE]
  │
  ├─ MQTT 메시지 수신 ───────────> [HANDLING]
  │                                     │
  │                                     ├─ 텔레메트리 저장
  │                                     ├─ 상태 업데이트
  │                                     ├─ 진단 결과 처리
  │                                     └─ 완료 ──> [IDLE]
  │
  └─ 타이머 이벤트 ──────────────> [MAINTENANCE]
                                        │
                                        ├─ 주기적 체크
                                        ├─ 로그 정리
                                        ├─ 통계 업데이트
                                        └─ 완료 ──> [IDLE]
```

---

## 5. 핵심 특징

### ✅ 이벤트 기반 (Event-Driven)

```python
# server/main.py
async def start(self):
    # 서버 시작
    mqtt_task = asyncio.create_task(start_mqtt_server(...))
    https_task = asyncio.create_task(start_https_server(...))
    
    # 이벤트 대기
    await self.shutdown_event.wait()  # ← 여기서 계속 대기
```

- 서버는 시작 후 **이벤트 루프에서 대기**
- 요청이 오면 **비동기로 처리**
- 처리 완료 후 **다시 대기 상태**

### ✅ 비동기 처리 (Async I/O)

```python
# server/https_server.py
@app.post("/api/v1/vehicles/{vin}/vci")
async def update_vci(vin: str, vci_data: dict):
    # 비동기로 VCI 분석
    outdated_ecus = await self._analyze_vci(vci_data)
    return {"outdated_ecus": outdated_ecus}
```

- 여러 VMG가 동시에 요청해도 **병렬 처리**
- I/O 대기 중에도 **다른 요청 처리 가능**

### ✅ Pub/Sub 패턴 (MQTT)

```python
# server/mqtt_server.py
async def _handle_message(self, message):
    # 토픽별로 자동 라우팅
    if 'telemetry' in message.topic:
        await self._handle_telemetry(message)
    elif 'diagnostics' in message.topic:
        await self._handle_diagnostics(message)
```

- VMG가 **토픽에 메시지 발행**
- 서버가 **Subscribe한 토픽 자동 수신**
- 실시간 양방향 통신

---

## 6. 데이터 흐름

### VMG → Server (업로드)

```
VMG                          Server
 │                             │
 │  [HTTPS]                    │
 │  - VCI (JSON)               │
 │  - Metadata (JSON)          │
 │  - Diagnostic Results       │
 │──────────────────────────> │
 │                             │
 │  [MQTT]                     │
 │  - Telemetry (JSON)         │
 │  - OTA Status (JSON)        │
 │  - Heartbeat                │
 │──────────────────────────> │
 │                             │
```

### Server → VMG (다운로드)

```
Server                       VMG
 │                             │
 │  [HTTPS]                    │
 │  - Firmware Package (Binary)│
 │  - Configuration (JSON)     │
 │  - Update Manifest          │
 │ <──────────────────────────│
 │                             │
 │  [MQTT]                     │
 │  - Control Commands (JSON)  │
 │  - Diagnostic Requests      │
 │  - Remote Config            │
 │ <──────────────────────────│
 │                             │
```

---

## 7. 프로세스 요약

### 질문: "Default 상태에서 쭉 대기하다가 핸드셰이크나 .json 파일이 날아오면 감지하고 대응?"

### 답변: **정확합니다!**

1. **서버 시작**
   - MQTT 서버: Port 8883 Listen
   - HTTPS 서버: Port 8443 Listen
   - 이벤트 루프 대기

2. **VMG 연결**
   - PQC-TLS Handshake (ML-KEM-768 + ECDSA)
   - mTLS 인증서 검증
   - 연결 성공

3. **요청 처리**
   - **HTTPS**: JSON 요청 수신 → 처리 → JSON 응답
   - **MQTT**: JSON 메시지 수신 → 처리 → (필요시) JSON 발행

4. **다시 대기**
   - 연결 유지 (MQTT Keepalive)
   - 다음 요청 대기

---

## 8. 실제 실행 예시

```bash
$ python -m server.main

╔═══════════════════════════════════════════════════════════╗
║              OTA Server with PQC-Hybrid TLS               ║
╚═══════════════════════════════════════════════════════════╝

[2025-10-31 10:00:00] INFO - OTA Server Starting
[2025-10-31 10:00:00] INFO - Initializing PQC Manager...
[2025-10-31 10:00:00] INFO -   Loaded 13 PQC configurations
[2025-10-31 10:00:00] INFO -   Default: ML-KEM-768 + ECDSA-P256
[2025-10-31 10:00:01] INFO - Starting MQTT Server...
[2025-10-31 10:00:01] INFO - MQTT server started on 0.0.0.0:8883
[2025-10-31 10:00:01] INFO - Starting HTTPS Server...
[2025-10-31 10:00:01] INFO - HTTPS server started on 0.0.0.0:8443
[2025-10-31 10:00:01] INFO - OTA Server Running
[2025-10-31 10:00:01] INFO - Active Services: MQTT, HTTPS
[2025-10-31 10:00:01] INFO - Press Ctrl+C to stop

# ← 여기서 대기 중...

[2025-10-31 10:05:23] INFO - [MQTT] New connection from 192.168.1.100
[2025-10-31 10:05:23] INFO - [MQTT] TLS handshake successful (ML-KEM-768)
[2025-10-31 10:05:24] INFO - [MQTT] Received message on vehicle/VMG-001/telemetry
[2025-10-31 10:05:24] INFO - [MQTT] Telemetry from VMG-001 stored

[2025-10-31 10:10:15] INFO - [HTTPS] POST /api/v1/vehicles/VMG-001/vci
[2025-10-31 10:10:15] INFO - [HTTPS] Analyzing VCI for VMG-001
[2025-10-31 10:10:15] INFO - [HTTPS] Found 3 outdated ECUs
[2025-10-31 10:10:15] INFO - [HTTPS] Response sent

# ← 다시 대기 중...
```

---

**결론**: OTA 서버는 **이벤트 기반 비동기 서버**로, 시작 후 대기 상태에서 VMG의 요청(HTTPS) 또는 메시지(MQTT)를 감지하면 즉시 처리하고 다시 대기 상태로 돌아갑니다.


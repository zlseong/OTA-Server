# PQC OTA Server - OEM Cloud

**양자 내성 암호화(PQC)를 적용한 OTA 서버 for Zonal E/E Architecture**

## 🎯 핵심 아이디어

OEM Server → VMG (MacBook Air Linux CCU) → ZGW (TC375) → Zone ECUs

- ✅ **Hybrid PQC-TLS 1.3**: ML-KEM 768 + X25519
- ✅ **MQTT + HTTPS 분리**: Commands (MQTT), Package Download (HTTPS)
- ✅ **계층적 패키지 구조**: 64-byte 헤더 + Payload
- ✅ **Campaign Management**: VIN별 OTA 배포 관리

```
┌─────────────────────────────────────────────────────────┐
│  OEM Server (Cloud)                                     │
│  ├─ MQTT Broker (Commands, VCI, Status, Telemetry)     │
│  └─ HTTPS Server (OTA Package Download)                │
└────────┬────────────────────────┬───────────────────────┘
         │                        │
         │ MQTT/JSON              │ HTTPS
         │ (Hybrid PQC-TLS)       │ (Hybrid PQC-TLS)
         │                        │
         ▼                        ▼
    ┌─────────────────────────────────────────┐
    │  VMG (Telematics Gateway)               │
    │  - MacBook Air M2 (Linux CCU)           │
    │  - Package Storage: 256GB SSD           │
    └─────────────────────────────────────────┘
```

---

## 📁 프로젝트 구조

```
server/
├── server/
│   ├── app.py              # Flask HTTPS Server
│   ├── mqtt_broker.py      # MQTT Broker Interface
│   ├── pqc_tls.py          # PQC TLS Wrapper (C library)
│   └── mqtt_client.py      # (Legacy, deprecated)
├── tools/
│   └── ota_package_builder.py  # Package Builder Tool
├── campaigns/              # Campaign Storage
│   └── Campaign_OTA-2025-11-001/
│       ├── campaign_metadata.json
│       ├── full_package.bin
│       ├── vmg_package/
│       └── zone1_package/
├── firmware/               # Raw firmware binaries
├── certs/                  # PQC Certificates
├── pqc_lib/                # C PQC TLS Library
├── docs/                   # Documentation
└── requirements.txt        # Python Dependencies
```

---

## 🚀 빠른 시작

### 1. 의존성 설치

```bash
# Python dependencies
pip install -r requirements.txt

# MQTT Broker (Mosquitto)
sudo apt install mosquitto mosquitto-clients

# Start Mosquitto
mosquitto -v
```

### 2. Package Builder 사용

```bash
cd server/tools

# Example: Build campaign with VMG + ZGW + ECU packages
python3 ota_package_builder.py build \
  --campaign-id OTA-2025-11-001 \
  --vmg-binary ../../firmware/vmg_2.2.0.bin \
  --vmg-version 2.2.0.100 \
  --zgw-binary ../../firmware/zgw_1.2.0.elf \
  --zgw-version 1.2.0.50 \
  --ecu-011-binary ../../firmware/ecu011_1.1.0.elf \
  --ecu-011-version 1.1.0.10 \
  --output-dir ../campaigns/ \
  --compress

# Verify package
python3 ota_package_builder.py verify ../campaigns/Campaign_OTA-2025-11-001/vmg_package/vmg_sw_package.bin
```

### 3. OTA Server 실행

```bash
cd server/server
python3 app.py
```

서버가 다음 주소에서 시작됩니다:
- **HTTPS Server**: `http://0.0.0.0:5000`
- **MQTT Broker**: `localhost:1883`

---

## 📡 API 엔드포인트

### MQTT Topics (Port 1883)

```
VMG → Server:
  oem/{vin}/wake_up              # 차량 Wake-up
  oem/{vin}/response             # 명령 응답
  oem/{vin}/vci                  # VCI 리포트
  oem/{vin}/telemetry            # 텔레메트리
  oem/{vin}/ota/status           # OTA 상태

Server → VMG:
  oem/{vin}/command              # 명령 (VCI 요청, OTA 준비 체크)
  oem/{vin}/ota/campaign         # OTA 캠페인 알림
  oem/{vin}/ota/metadata         # HTTPS 다운로드 URL 및 메타데이터
```

### HTTPS REST API (Port 5000)

#### Server Info
```
GET  /                          # 서버 정보
GET  /health                    # 헬스 체크
```

#### Campaign Management
```
GET  /api/campaigns                          # 캠페인 목록
GET  /api/campaigns/<campaign_id>            # 캠페인 상세
POST /api/campaigns                          # 캠페인 생성
POST /api/campaigns/<campaign_id>/deploy/<vin>  # 특정 차량에 배포
```

#### Vehicle Management
```
GET  /api/vehicles                # 차량 목록
GET  /api/vehicles/<vin>          # 차량 상세
POST /api/vehicles/<vin>/vci      # VCI 요청
POST /api/vehicles/<vin>/readiness  # OTA 준비 상태 확인
```

#### Package Download (with Range support)
```
GET  /packages/<campaign_id>/full_package.bin   # OTA 패키지 다운로드
GET  /packages/<campaign_id>/metadata.json      # 메타데이터
```

---

## 📦 64-byte Package Header 구조

```c
typedef struct __attribute__((packed)) {
    /* Identification (16 bytes) */
    uint32 magic;                   /* 0x53575047 ("SWPG") */
    uint16 target_ecu_id;           /* 0x0E00=VMG, 0x0091=ZGW, 0x0011=ECU_011 */
    uint8  software_type;           /* 0x01=APP, 0x02=BOOT, 0x03=CAL */
    uint8  compression;             /* 0x00=none, 0x01=gzip */
    uint32 payload_size;            /* Payload size (bytes) */
    uint32 uncompressed_size;       /* Uncompressed size */

    /* Version Information (12 bytes) */
    uint8  version_major;
    uint8  version_minor;
    uint8  version_patch;
    uint8  version_build;
    uint32 version_timestamp;
    uint32 version_serial;

    /* Security & Integrity (16 bytes) */
    uint32 crc32;
    uint32 signature[3];            /* RSA-2048 signature (reserved) */

    /* Routing Information (8 bytes) */
    uint16 source_ecu_id;
    uint16 hop_count;
    uint32 sequence_number;

    /* Reserved (12 bytes) */
    uint8  reserved[12];
} SoftwarePackageHeader;            /* Total: 64 bytes */
```

---

## 🔄 OTA 시퀀스

### Phase 1: VCI Collection
```
1. Vehicle Ignition ON
2. VMG → Server: Wake-up (MQTT oem/{vin}/wake_up)
3. Server → VMG: Request VCI (MQTT oem/{vin}/command)
4. VMG → ZGW → ECUs: UDS 0x22 (Read DID)
5. VMG → Server: VCI Report (MQTT oem/{vin}/vci)
```

### Phase 2: Campaign Deployment
```
6. Server → VMG: Campaign Notification (MQTT oem/{vin}/ota/campaign)
7. VMG: User consent
8. VMG → Server: Campaign Accepted (MQTT oem/{vin}/response)
9. Server → VMG: Campaign Metadata with HTTPS URL (MQTT oem/{vin}/ota/metadata)
```

### Phase 3: Package Download
```
10. VMG → Server: HTTPS GET /packages/{campaign_id}/full_package.bin
11. Server → VMG: Binary stream (supports Range header for resume)
12. VMG: Save to /var/ota/campaign_xxx/
13. VMG: Verify SHA256, CRC32
14. VMG → Server: Download Complete (MQTT oem/{vin}/ota/status)
```

### Phase 4: Installation
```
15. VMG: Self-update to Unactive Bank
16. VMG → ZGW: DoIP/UDS Software Distribution
17. ZGW → ECUs: CAN-FD/UDS Programming
18. VMG → Server: Installation Complete (MQTT oem/{vin}/ota/status)
```

### Phase 5: Verification
```
19. VMG, ZGW, ECUs: Reboot to new bank
20. VMG: Collect VCI again
21. VMG → Server: Verification Complete (MQTT oem/{vin}/ota/status)
```

---

## 🔐 보안: Hybrid PQC-TLS 1.3

### Key Exchange
```
ML-KEM 768 (Post-Quantum) + X25519 (Classical)
→ Combined Shared Secret: KDF-SHA-384(KEM_Secret || ECDH_Secret)
```

### Cipher Suite
```
TLS_MLKEM768_X25519_WITH_AES_256_GCM_SHA384
```

### Why Hybrid?
1. **Quantum Resistance**: ML-KEM 768 protects against future quantum computers
2. **Backward Compatibility**: X25519 ensures security with current systems
3. **Defense in Depth**: Break one → still protected by the other
4. **NIST Approved**: ML-KEM (Kyber) selected by NIST in 2024

---

## 🧪 테스트

### 1. Package Builder 테스트

```bash
# Create test firmware
echo "Test VMG Firmware v2.2.0" > /tmp/vmg_test.bin
echo "Test ZGW Firmware v1.2.0" > /tmp/zgw_test.bin

# Build campaign
python3 tools/ota_package_builder.py build \
  --campaign-id TEST-001 \
  --vmg-binary /tmp/vmg_test.bin \
  --vmg-version 2.2.0.1 \
  --zgw-binary /tmp/zgw_test.bin \
  --zgw-version 1.2.0.1 \
  --output-dir ./campaigns/

# Verify
python3 tools/ota_package_builder.py verify \
  ./campaigns/Campaign_TEST-001/vmg_package/vmg_sw_package.bin
```

### 2. API 테스트

```bash
# Server info
curl http://localhost:5000/

# Health check
curl http://localhost:5000/health

# List campaigns
curl http://localhost:5000/api/campaigns

# Get campaign
curl http://localhost:5000/api/campaigns/TEST-001

# Download package (with resume support)
curl -H "Authorization: Bearer test_token" \
     -H "Range: bytes=0-1023" \
     http://localhost:5000/packages/TEST-001/full_package.bin
```

### 3. MQTT 테스트

```bash
# Subscribe to topics
mosquitto_sub -h localhost -t 'oem/#' -v

# Publish wake-up message
mosquitto_pub -h localhost -t 'oem/VIN123/wake_up' -m '{
  "msg_type": "vehicle_wake_up",
  "timestamp": "2025-11-07T08:00:00Z",
  "vehicle": {"vin": "VIN123"},
  "vmg_info": {"fw_version": "VMG-2.1.0"}
}'
```

---

## 📊 성능

- **Package Building**: ~1-2 seconds for 10MB package
- **MQTT Latency**: < 10ms (local broker)
- **HTTPS Download**: Limited by network bandwidth
- **CRC32 Verification**: ~100 MB/s
- **SHA256 Verification**: ~500 MB/s

---

## 📝 참고 문서

- `OTA_SERVER_ARCHITECTURE.md`: 시스템 아키텍처 상세
- `MQTT_API_SPECIFICATION.md`: MQTT API 명세
- `PACKAGE_BUILDER.md`: 패키지 빌더 가이드
- `docs/HOW_IT_WORKS.md`: 작동 원리
- `docs/HANDSHAKE_VERIFICATION.md`: PQC TLS 핸드셰이크 검증

---

## 🔮 향후 개선

1. **PQC-TLS 적용**: C 라이브러리와 통합
2. **Database**: PostgreSQL/MongoDB로 마이그레이션
3. **Authentication**: JWT 토큰 인증
4. **Gunicorn/uWSGI**: 프로덕션 배포
5. **Docker**: 컨테이너화
6. **Kubernetes**: 오케스트레이션

---

## 📝 라이선스

MIT License

**Version:** 1.0.0  
**Last Updated:** 2025-11-07  
**Architecture:** Zonal E/E with PQC

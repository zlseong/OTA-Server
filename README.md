# OTA Server with PQC-Hybrid TLS

Secure OTA (Over-The-Air) update server for automotive ECUs with Post-Quantum Cryptography support.

## Features

### 1. ECU Version Management
- Supports 100 ECUs (ECU_001 ~ ECU_100)
- Semantic versioning (x.y.z) tracking
- Automatic version comparison and update detection
- Individual and batch update management

### 2. PQC-Hybrid TLS Support
- 13 predefined PQC configurations
- ML-KEM (512, 768, 1024) + ML-DSA/ECDSA combinations
- Compatible with VMG_and_MCUs project
- Configurable security levels

### 3. Server Components
- **MQTT Server**: Real-time control and telemetry
- **HTTPS Server**: Secure firmware package delivery
- **REST API**: Management interface

### 4. Update Package Management
- VCI (Vehicle Configuration Information) analysis
- Metadata-based version detection
- Automated package assembly per Zonal Gateway
- Delta updates support

### 5. Remote Diagnostics
- Remote diagnostic message injection to VMG
- Zonal Gateway-based ECU diagnostics
- Diagnostic result aggregation
- UDS (ISO 14229) support

### 6. Package Distribution
- Decryption and hash verification
- Target ECU identification
- Zonal Gateway-optimized packaging
- Parallel distribution support

## Architecture

```
OTA Server (Ubuntu WSL)
├── MQTT Server (Port 1883/8883)
│   ├── Vehicle telemetry
│   ├── Command & control
│   └── Diagnostic messages
├── HTTPS Server (Port 443)
│   ├── Firmware packages
│   ├── Metadata distribution
│   └── REST API
└── Database
    ├── ECU registry (001-100)
    ├── Version tracking
    └── Update history

↕ PQC-TLS (ML-KEM + ML-DSA/ECDSA)

VMG (Vehicle Gateway)
├── Package decryption
├── Hash verification
├── Target identification
└── Distribution to ZGs

↕ DoIP/UDS (In-vehicle)

Zonal Gateways (ZG1, ZG2, ...)
├── Zone management
├── ECU diagnostics
└── Update distribution

↕ CAN/Ethernet

ECUs (ECU_001 ~ ECU_100)
```

## System Requirements

### Server
- OS: Ubuntu 20.04+ (WSL2 recommended)
- Python: 3.9+
- RAM: 4GB minimum
- Storage: 100GB+ (for firmware packages)

### Dependencies
- OpenSSL 3.0+ (with PQC support)
- PostgreSQL 14+ (ECU database)
- Redis 6+ (caching)
- Mosquitto 2.0+ (MQTT broker)

## Quick Start

### 1. Installation

```bash
# Clone repository
git clone https://github.com/zlseong/OTA-Server.git
cd OTA-Server

# Install dependencies
pip install -r requirements.txt

# Initialize database
python scripts/init_db.py

# Generate PQC certificates
./scripts/generate_pqc_certs.sh
```

### 2. Configuration

```bash
# Edit configuration
cp config/server.yaml.example config/server.yaml
vim config/server.yaml
```

### 3. Run Server

```bash
# Start all services
python server/main.py

# Or start individually
python server/mqtt_server.py &
python server/https_server.py &
python server/diagnostics_server.py &
```

## Project Structure

```
OTA-Server/
├── server/
│   ├── main.py                 # Main entry point
│   ├── mqtt_server.py          # MQTT broker integration
│   ├── https_server.py         # HTTPS/REST API server
│   ├── diagnostics_server.py   # Diagnostic message handler
│   ├── package_manager.py      # Update package manager
│   ├── version_manager.py      # ECU version tracker
│   └── pqc_manager.py          # PQC configuration manager
├── models/
│   ├── ecu.py                  # ECU model
│   ├── vehicle.py              # Vehicle model
│   ├── package.py              # Firmware package model
│   └── diagnostic.py           # Diagnostic message model
├── api/
│   ├── routes.py               # REST API routes
│   ├── auth.py                 # Authentication
│   └── validation.py           # Request validation
├── database/
│   ├── schema.sql              # Database schema
│   ├── migrations/             # Database migrations
│   └── queries.py              # SQL queries
├── crypto/
│   ├── pqc_wrapper.py          # PQC library wrapper
│   ├── tls_server.py           # TLS server implementation
│   └── certificate_manager.py  # Certificate management
├── config/
│   ├── server.yaml             # Server configuration
│   ├── pqc_configs.yaml        # PQC parameter configurations
│   └── ecu_registry.yaml       # ECU registry
├── scripts/
│   ├── init_db.py              # Database initialization
│   ├── generate_pqc_certs.sh   # Certificate generation
│   └── seed_ecus.py            # Seed ECU data
├── tests/
│   ├── test_mqtt.py
│   ├── test_https.py
│   ├── test_package_manager.py
│   └── test_pqc.py
├── docs/
│   ├── API.md                  # API documentation
│   ├── MESSAGE_FORMAT.md       # Message format spec
│   └── DEPLOYMENT.md           # Deployment guide
├── requirements.txt            # Python dependencies
├── Dockerfile                  # Docker image
├── docker-compose.yml          # Multi-container setup
└── README.md

```

## Message Format

Uses Unified Message Format compatible with VMG_and_MCUs project.
See [docs/MESSAGE_FORMAT.md](docs/MESSAGE_FORMAT.md) for details.

## PQC Configurations

13 predefined configurations (compatible with VMG_and_MCUs):

| ID | KEM | Signature | Security | Use Case |
|----|-----|-----------|----------|----------|
| 0 | X25519 | ECDSA-P256 | Classical | Baseline |
| 1 | ML-KEM-512 | ECDSA-P256 | 128-bit | Hybrid lightweight |
| **2** | **ML-KEM-768** | **ECDSA-P256** | **192-bit** | **Default (Hybrid)** |
| 3 | ML-KEM-1024 | ECDSA-P256 | 256-bit | Hybrid high-security |
| 4-6 | ML-KEM-512 | ML-DSA-44/65/87 | 128-bit | Pure PQC |
| 7-9 | ML-KEM-768 | ML-DSA-44/65/87 | 192-bit | Pure PQC |
| 10-12 | ML-KEM-1024 | ML-DSA-44/65/87 | 256-bit | Pure PQC high-security |

Default: **Config #2 (ML-KEM-768 + ECDSA-P256)**

## API Endpoints

### Vehicle Management
- `POST /api/v1/vehicles/register` - Register new vehicle
- `GET /api/v1/vehicles/{vin}` - Get vehicle info
- `POST /api/v1/vehicles/{vin}/vci` - Update VCI

### ECU Management
- `GET /api/v1/ecus` - List all ECUs
- `GET /api/v1/ecus/{ecu_id}` - Get ECU info
- `PUT /api/v1/ecus/{ecu_id}/version` - Update ECU version

### OTA Updates
- `POST /api/v1/ota/check` - Check for updates
- `POST /api/v1/ota/package` - Create update package
- `GET /api/v1/ota/package/{package_id}` - Download package
- `POST /api/v1/ota/status` - Report update status

### Diagnostics
- `POST /api/v1/diagnostics/send` - Send diagnostic message
- `GET /api/v1/diagnostics/results/{request_id}` - Get results

## Development

### Run Tests
```bash
pytest tests/
```

### Code Style
```bash
black server/ models/ api/
flake8 server/ models/ api/
```

### Docker Development
```bash
docker-compose up -d
docker-compose logs -f
```

## Security

- All communications use PQC-TLS
- Firmware packages are signed with ML-DSA
- Multi-layer authentication (mTLS + API keys)
- Role-based access control (RBAC)
- Audit logging

## Related Projects

- [VMG_and_MCUs](https://github.com/zlseong/VMG_and_MCUs.git) - Vehicle Gateway & MCU implementation
- [OTA-Project-with-PQC-hybrid-TLS](https://github.com/zlseong/OTA-Project-with-PQC-hybrid-TLS.git) - Reference implementation

## License

MIT

## Contributors

- [Your Name]

## Contact

- GitHub: [@zlseong](https://github.com/zlseong)

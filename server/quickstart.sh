#!/bin/bash

# PQC OTA Python Server - Quick Start

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

echo "╔════════════════════════════════════════════════════════════╗"
echo "║   PQC OTA Server - Quick Start (Python + C)               ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# 1. C 라이브러리 빌드
log_step "1/5 Building C PQC TLS library..."
cd pqc_lib
make clean && make
make install
cd ..
log_info "C library built: pqc_lib/libpqc_tls.so"
echo ""

# 2. Python 의존성 설치
log_step "2/5 Installing Python dependencies..."
pip3 install -r requirements.txt
log_info "Python packages installed"
echo ""

# 3. 디렉토리 생성
log_step "3/5 Creating directories..."
mkdir -p firmware certs
log_info "Directories created"
echo ""

# 4. 테스트 펌웨어 생성
log_step "4/5 Creating test firmware..."
echo "Test Firmware v1.0.0" > firmware/firmware_v1.0.0.bin
log_info "Test firmware created: firmware/firmware_v1.0.0.bin"
echo ""

# 5. 서버 실행
log_step "5/5 Starting Flask server..."
cd server
echo ""
log_info "Server starting on http://0.0.0.0:5000"
log_info "Press Ctrl+C to stop"
echo ""
python3 app.py




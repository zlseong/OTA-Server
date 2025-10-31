#!/bin/bash
# OTA Server Startup Script

set -e

echo "=========================================="
echo "OTA Server Startup"
echo "=========================================="

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python version: $PYTHON_VERSION"

# Check if Python 3.10+
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]); then
    echo "Error: Python 3.10+ required"
    exit 1
fi

# Check OpenSSL version
OPENSSL_VERSION=$(openssl version | awk '{print $2}')
echo "OpenSSL version: $OPENSSL_VERSION"

if ! echo "$OPENSSL_VERSION" | grep -q "^3\."; then
    echo "Warning: OpenSSL 3.x recommended for PQC support"
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo ""
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install/Update dependencies
echo ""
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Check configuration
if [ ! -f "config/server.yaml" ]; then
    echo ""
    echo "Warning: config/server.yaml not found"
    echo "Using config/server.yaml.example"
    
    if [ ! -f "config/server.yaml.example" ]; then
        echo "Error: config/server.yaml.example not found"
        exit 1
    fi
fi

# Check database connection
echo ""
echo "Checking database connection..."
# TODO: Add database connection check

# Check certificates (if TLS enabled)
echo ""
echo "Checking PQC certificates..."
if [ -d "certs" ] && [ -f "certs/ca_cert.pem" ]; then
    echo "  CA certificate: Found"
else
    echo "  Warning: PQC certificates not found"
    echo "  Run: ./scripts/generate_pqc_certs.sh"
fi

# Create necessary directories
echo ""
echo "Creating directories..."
mkdir -p logs
mkdir -p packages
mkdir -p temp

echo ""
echo "=========================================="
echo "Starting OTA Server..."
echo "=========================================="
echo ""

# Run server
python3 -m server.main

# Deactivate on exit
deactivate


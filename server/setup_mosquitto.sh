#!/bin/bash
# Mosquitto Setup Script for PQC OTA Server

set -e

echo "╔════════════════════════════════════════════════════════════╗"
echo "║        Mosquitto MQTT Broker Setup                        ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Check if running with sudo
if [ "$EUID" -ne 0 ]; then 
    echo "⚠️  This script needs sudo privileges for some operations"
    echo "Run: sudo $0"
    exit 1
fi

# ==================== Fix Broken Packages ====================

echo "[0/7] Fixing broken packages..."
apt --fix-broken install -y
echo "✓ Package dependencies fixed"

# ==================== Install Mosquitto ====================

echo ""
echo "[1/7] Installing Mosquitto MQTT Broker..."

if command -v mosquitto &> /dev/null; then
    echo "✓ Mosquitto already installed"
    mosquitto -h | head -n 1
else
    echo "Installing Mosquitto..."
    apt update
    apt install -y mosquitto mosquitto-clients
    echo "✓ Mosquitto installed"
fi

# ==================== Create Directories ====================

echo ""
echo "[2/7] Creating directories..."

mkdir -p /etc/mosquitto/certs
mkdir -p /var/lib/mosquitto
mkdir -p /var/log/mosquitto

chown -R mosquitto:mosquitto /var/lib/mosquitto
chown -R mosquitto:mosquitto /var/log/mosquitto

echo "✓ Directories created"

# ==================== Copy Configuration ====================

echo ""
echo "[3/7] Installing configuration files..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -f "$SCRIPT_DIR/mosquitto.conf" ]; then
    cp "$SCRIPT_DIR/mosquitto.conf" /etc/mosquitto/mosquitto.conf
    echo "✓ mosquitto.conf installed"
else
    echo "⚠️  mosquitto.conf not found in $SCRIPT_DIR"
fi

if [ -f "$SCRIPT_DIR/mosquitto_acl.conf" ]; then
    cp "$SCRIPT_DIR/mosquitto_acl.conf" /etc/mosquitto/acl.conf
    echo "✓ ACL configuration installed"
else
    echo "⚠️  mosquitto_acl.conf not found"
fi

# ==================== Create Password File ====================

echo ""
echo "[4/7] Creating password file..."

if [ ! -f /etc/mosquitto/passwd ]; then
    # Create OEM server user
    mosquitto_passwd -c -b /etc/mosquitto/passwd oem_server "oem_server_password_123"
    
    # Create example VMG users
    mosquitto_passwd -b /etc/mosquitto/passwd vmg_VIN123 "vmg_password_123"
    mosquitto_passwd -b /etc/mosquitto/passwd vmg_VIN456 "vmg_password_456"
    
    echo "✓ Password file created"
    echo "  Users: oem_server, vmg_VIN123, vmg_VIN456"
else
    echo "✓ Password file already exists"
fi

# ==================== Generate Test Certificates ====================

echo ""
echo "[5/7] Generating test certificates (self-signed)..."

CERT_DIR="/etc/mosquitto/certs"

if [ ! -f "$CERT_DIR/ca.crt" ]; then
    # Generate CA
    openssl req -new -x509 -days 3650 -extensions v3_ca \
        -keyout "$CERT_DIR/ca.key" -out "$CERT_DIR/ca.crt" \
        -subj "/C=KR/ST=Seoul/L=Seoul/O=OEM/CN=OEM-CA" \
        -nodes
    
    # Generate server key and CSR
    openssl genrsa -out "$CERT_DIR/server.key" 2048
    openssl req -new -key "$CERT_DIR/server.key" \
        -out "$CERT_DIR/server.csr" \
        -subj "/C=KR/ST=Seoul/L=Seoul/O=OEM/CN=mqtt.oem-server.com"
    
    # Sign server certificate
    openssl x509 -req -in "$CERT_DIR/server.csr" \
        -CA "$CERT_DIR/ca.crt" -CAkey "$CERT_DIR/ca.key" \
        -CAcreateserial -out "$CERT_DIR/server.crt" \
        -days 3650
    
    # Set permissions
    chown -R mosquitto:mosquitto "$CERT_DIR"
    chmod 600 "$CERT_DIR"/*.key
    
    # Clean up
    rm "$CERT_DIR/server.csr"
    
    echo "✓ Test certificates generated"
    echo "  WARNING: These are self-signed certificates for testing only!"
else
    echo "✓ Certificates already exist"
fi

# ==================== Enable and Start Service ====================

echo ""
echo "[6/7] Configuring systemd service..."

# Enable Mosquitto service
systemctl enable mosquitto

# Restart Mosquitto
systemctl restart mosquitto

# Check status
if systemctl is-active --quiet mosquitto; then
    echo "✓ Mosquitto service is running"
else
    echo "❌ Mosquitto service failed to start"
    systemctl status mosquitto
    exit 1
fi

# ==================== Firewall Configuration ====================

echo ""
echo "[7/7] Configuring firewall..."

if command -v ufw &> /dev/null; then
    ufw allow 1883/tcp comment 'MQTT'
    ufw allow 8883/tcp comment 'MQTT over TLS'
    ufw allow 9001/tcp comment 'MQTT over WebSocket'
    echo "✓ Firewall rules added (ufw)"
else
    echo "⚠️  ufw not found, skipping firewall configuration"
fi

# ==================== Summary ====================

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║        Mosquitto Setup Complete                            ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "Configuration:"
echo "  • Config file:    /etc/mosquitto/mosquitto.conf"
echo "  • ACL file:       /etc/mosquitto/acl.conf"
echo "  • Password file:  /etc/mosquitto/passwd"
echo "  • Certificates:   /etc/mosquitto/certs/"
echo ""
echo "Ports:"
echo "  • 1883  - MQTT (non-TLS)"
echo "  • 8883  - MQTT over TLS"
echo "  • 9001  - MQTT over WebSocket"
echo ""
echo "Users:"
echo "  • oem_server    / oem_server_password_123"
echo "  • vmg_VIN123    / vmg_password_123"
echo "  • vmg_VIN456    / vmg_password_456"
echo ""
echo "Test commands:"
echo "  # Subscribe"
echo "  mosquitto_sub -h localhost -t 'oem/#' -v"
echo ""
echo "  # Publish (with auth)"
echo "  mosquitto_pub -h localhost -t 'oem/VIN123/wake_up' \\"
echo "    -u oem_server -P oem_server_password_123 \\"
echo "    -m '{\"msg_type\":\"vehicle_wake_up\"}'"
echo ""
echo "Service management:"
echo "  sudo systemctl status mosquitto"
echo "  sudo systemctl restart mosquitto"
echo "  sudo systemctl stop mosquitto"
echo ""
echo "Logs:"
echo "  sudo tail -f /var/log/mosquitto/mosquitto.log"
echo ""

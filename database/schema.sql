-- OTA Server Database Schema
-- PostgreSQL 14+

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================================
-- Vehicles Table
-- ============================================================================
CREATE TABLE vehicles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    vin VARCHAR(17) UNIQUE NOT NULL,
    vehicle_model VARCHAR(100) NOT NULL,
    vehicle_year INTEGER NOT NULL,
    vmg_id VARCHAR(50) UNIQUE NOT NULL,
    
    -- Network configuration
    ip_address INET,
    mac_address MACADDR,
    
    -- PQC Configuration
    pqc_config_id INTEGER DEFAULT 2,  -- Default: ML-KEM-768 + ECDSA
    
    -- Status
    status VARCHAR(20) DEFAULT 'active',  -- active, inactive, maintenance
    last_connected TIMESTAMP WITH TIME ZONE,
    
    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_vehicles_vin ON vehicles(vin);
CREATE INDEX idx_vehicles_vmg_id ON vehicles(vmg_id);
CREATE INDEX idx_vehicles_status ON vehicles(status);

-- ============================================================================
-- Zonal Gateways Table
-- ============================================================================
CREATE TABLE zonal_gateways (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    zg_id VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    vehicle_id UUID REFERENCES vehicles(id) ON DELETE CASCADE,
    
    -- Network
    ip_address INET NOT NULL,
    port INTEGER DEFAULT 13400,
    
    -- Status
    status VARCHAR(20) DEFAULT 'active',
    last_heartbeat TIMESTAMP WITH TIME ZONE,
    
    -- Metadata
    hardware_version VARCHAR(50),
    firmware_version VARCHAR(20),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_zg_vehicle ON zonal_gateways(vehicle_id);
CREATE INDEX idx_zg_status ON zonal_gateways(status);

-- ============================================================================
-- ECUs Table (ECU_001 ~ ECU_100)
-- ============================================================================
CREATE TABLE ecus (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ecu_id VARCHAR(20) UNIQUE NOT NULL,  -- ECU_001, ECU_002, ...
    name VARCHAR(100) NOT NULL,
    type VARCHAR(50) NOT NULL,  -- ECM, TCM, BCM, etc.
    
    -- Association
    vehicle_id UUID REFERENCES vehicles(id) ON DELETE CASCADE,
    zonal_gateway_id UUID REFERENCES zonal_gateways(id) ON DELETE SET NULL,
    
    -- Hardware
    hardware_type VARCHAR(50) NOT NULL,  -- TC375, etc.
    serial_number VARCHAR(100),
    mac_address MACADDR,
    
    -- Version Information
    current_version VARCHAR(20) NOT NULL,  -- Semantic versioning (x.y.z)
    bootloader_version VARCHAR(20),
    application_version VARCHAR(20),
    
    -- Status
    status VARCHAR(20) DEFAULT 'active',  -- active, updating, error, offline
    last_seen TIMESTAMP WITH TIME ZONE,
    
    -- Capabilities
    max_package_size BIGINT DEFAULT 104857600,  -- 100 MB
    supports_delta_update BOOLEAN DEFAULT true,
    supports_compression BOOLEAN DEFAULT true,
    
    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_ecus_ecu_id ON ecus(ecu_id);
CREATE INDEX idx_ecus_vehicle ON ecus(vehicle_id);
CREATE INDEX idx_ecus_zg ON ecus(zonal_gateway_id);
CREATE INDEX idx_ecus_status ON ecus(status);
CREATE INDEX idx_ecus_version ON ecus(current_version);

-- ============================================================================
-- Firmware Packages Table
-- ============================================================================
CREATE TABLE firmware_packages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    package_id VARCHAR(100) UNIQUE NOT NULL,
    
    -- Target ECU type
    ecu_type VARCHAR(50) NOT NULL,  -- ECM, TCM, etc.
    hardware_type VARCHAR(50) NOT NULL,
    
    -- Version
    version VARCHAR(20) NOT NULL,
    previous_version VARCHAR(20),  -- For delta updates
    
    -- Package info
    file_path VARCHAR(500) NOT NULL,
    file_size BIGINT NOT NULL,
    compressed_size BIGINT,
    compression_type VARCHAR(20),  -- none, gzip, zstd
    
    -- Security
    sha256_hash VARCHAR(64) NOT NULL,
    signature BYTEA NOT NULL,
    signature_algorithm VARCHAR(50) NOT NULL,  -- ML-DSA-65, ECDSA-P256
    
    -- Package type
    is_delta BOOLEAN DEFAULT false,
    is_rollback BOOLEAN DEFAULT false,
    
    -- Release info
    release_notes TEXT,
    release_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Status
    status VARCHAR(20) DEFAULT 'available',  -- available, deprecated, recalled
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_firmware_ecu_type ON firmware_packages(ecu_type);
CREATE INDEX idx_firmware_version ON firmware_packages(version);
CREATE INDEX idx_firmware_status ON firmware_packages(status);

-- ============================================================================
-- OTA Updates Table
-- ============================================================================
CREATE TABLE ota_updates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    update_id VARCHAR(100) UNIQUE NOT NULL,
    
    -- Target
    vehicle_id UUID REFERENCES vehicles(id) ON DELETE CASCADE,
    
    -- Package
    package_id UUID REFERENCES firmware_packages(id),
    
    -- ECU targets (JSON array)
    target_ecus JSONB NOT NULL,  -- ["ECU_001", "ECU_002", ...]
    
    -- Zonal Gateway distribution (JSON)
    zg_distribution JSONB,  -- {"ZG_POWERTRAIN": ["ECU_001"], ...}
    
    -- Status
    status VARCHAR(20) DEFAULT 'pending',  -- pending, in_progress, completed, failed, cancelled
    progress INTEGER DEFAULT 0,  -- 0-100
    
    -- Timing
    scheduled_at TIMESTAMP WITH TIME ZONE,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    
    -- Results
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    error_message TEXT,
    
    -- Metadata
    initiated_by VARCHAR(100),  -- user or system
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_ota_vehicle ON ota_updates(vehicle_id);
CREATE INDEX idx_ota_status ON ota_updates(status);
CREATE INDEX idx_ota_scheduled ON ota_updates(scheduled_at);

-- ============================================================================
-- OTA Update Details Table (per ECU)
-- ============================================================================
CREATE TABLE ota_update_details (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ota_update_id UUID REFERENCES ota_updates(id) ON DELETE CASCADE,
    ecu_id UUID REFERENCES ecus(id) ON DELETE CASCADE,
    
    -- Version transition
    from_version VARCHAR(20),
    to_version VARCHAR(20) NOT NULL,
    
    -- Status
    status VARCHAR(20) DEFAULT 'pending',  -- pending, downloading, installing, verifying, completed, failed
    progress INTEGER DEFAULT 0,
    
    -- Timing
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    
    -- Results
    error_code VARCHAR(20),
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_ota_details_update ON ota_update_details(ota_update_id);
CREATE INDEX idx_ota_details_ecu ON ota_update_details(ecu_id);
CREATE INDEX idx_ota_details_status ON ota_update_details(status);

-- ============================================================================
-- Diagnostics Table
-- ============================================================================
CREATE TABLE diagnostics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    diagnostic_id VARCHAR(100) UNIQUE NOT NULL,
    
    -- Target
    vehicle_id UUID REFERENCES vehicles(id) ON DELETE CASCADE,
    zonal_gateway_id UUID REFERENCES zonal_gateways(id) ON DELETE SET NULL,
    ecu_id UUID REFERENCES ecus(id) ON DELETE SET NULL,
    
    -- Diagnostic info
    service_id VARCHAR(10) NOT NULL,  -- UDS service ID (0x10, 0x22, etc.)
    request_data BYTEA,
    response_data BYTEA,
    
    -- Status
    status VARCHAR(20) DEFAULT 'pending',  -- pending, in_progress, completed, failed, timeout
    
    -- Timing
    sent_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    received_at TIMESTAMP WITH TIME ZONE,
    duration_ms INTEGER,
    
    -- Results
    success BOOLEAN,
    error_code VARCHAR(20),
    error_message TEXT,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_diagnostics_vehicle ON diagnostics(vehicle_id);
CREATE INDEX idx_diagnostics_ecu ON diagnostics(ecu_id);
CREATE INDEX idx_diagnostics_status ON diagnostics(status);
CREATE INDEX idx_diagnostics_sent ON diagnostics(sent_at);

-- ============================================================================
-- VCI (Vehicle Configuration Information) Table
-- ============================================================================
CREATE TABLE vci_snapshots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    vehicle_id UUID REFERENCES vehicles(id) ON DELETE CASCADE,
    
    -- VCI Data (JSON)
    vci_data JSONB NOT NULL,
    
    -- Analysis results
    outdated_ecus JSONB,  -- ECU IDs that need update
    update_priority INTEGER,  -- 0=low, 1=medium, 2=high, 3=critical
    
    -- Timestamp
    snapshot_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_vci_vehicle ON vci_snapshots(vehicle_id);
CREATE INDEX idx_vci_snapshot ON vci_snapshots(snapshot_at);

-- ============================================================================
-- Audit Log Table
-- ============================================================================
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Event info
    event_type VARCHAR(50) NOT NULL,  -- ota_started, ecu_updated, diagnostic_sent, etc.
    event_data JSONB,
    
    -- Actor
    user_id VARCHAR(100),
    ip_address INET,
    
    -- Target
    vehicle_id UUID REFERENCES vehicles(id) ON DELETE SET NULL,
    ecu_id UUID REFERENCES ecus(id) ON DELETE SET NULL,
    
    -- Timestamp
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_audit_event ON audit_logs(event_type);
CREATE INDEX idx_audit_vehicle ON audit_logs(vehicle_id);
CREATE INDEX idx_audit_created ON audit_logs(created_at);

-- ============================================================================
-- Triggers for updated_at
-- ============================================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_vehicles_updated_at BEFORE UPDATE ON vehicles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_zg_updated_at BEFORE UPDATE ON zonal_gateways
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_ecus_updated_at BEFORE UPDATE ON ecus
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_firmware_updated_at BEFORE UPDATE ON firmware_packages
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_ota_updated_at BEFORE UPDATE ON ota_updates
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- Views for convenience
-- ============================================================================

-- ECU with latest version info
CREATE VIEW v_ecu_versions AS
SELECT 
    e.ecu_id,
    e.name,
    e.type,
    e.current_version,
    fp.version AS latest_version,
    CASE 
        WHEN e.current_version < fp.version THEN true
        ELSE false
    END AS update_available,
    fp.id AS latest_package_id
FROM ecus e
LEFT JOIN LATERAL (
    SELECT id, version
    FROM firmware_packages
    WHERE ecu_type = e.type 
    AND status = 'available'
    ORDER BY version DESC
    LIMIT 1
) fp ON true;

-- OTA Update Summary
CREATE VIEW v_ota_summary AS
SELECT 
    ou.update_id,
    v.vin,
    v.vehicle_model,
    ou.status,
    ou.progress,
    COUNT(oud.id) AS total_ecus,
    SUM(CASE WHEN oud.status = 'completed' THEN 1 ELSE 0 END) AS completed_ecus,
    SUM(CASE WHEN oud.status = 'failed' THEN 1 ELSE 0 END) AS failed_ecus,
    ou.started_at,
    ou.completed_at
FROM ota_updates ou
JOIN vehicles v ON ou.vehicle_id = v.id
LEFT JOIN ota_update_details oud ON ou.id = oud.ota_update_id
GROUP BY ou.id, v.vin, v.vehicle_model;

-- ============================================================================
-- Sample Data (for development)
-- ============================================================================

-- Insert sample vehicle
INSERT INTO vehicles (vin, vehicle_model, vehicle_year, vmg_id, ip_address, status)
VALUES ('KMHGH4JH1NU123456', 'Genesis G80 EV', 2025, 'VMG-001', '192.168.1.1', 'active');


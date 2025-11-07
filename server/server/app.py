"""
PQC OTA Server - Flask Application
OEM Server for Zonal E/E Architecture
Implements MQTT_API_SPECIFICATION.md and OTA_SERVER_ARCHITECTURE.md
"""

from flask import Flask, jsonify, request, send_file, Response
import os
import json
import hashlib
import time
from datetime import datetime
from typing import Dict, List, Optional
import threading
from mqtt_broker import OTAMQTTBroker, example_handlers
from werkzeug.utils import secure_filename

app = Flask(__name__)

# ==================== Configuration ====================

# Directories
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
CAMPAIGNS_DIR = os.path.join(BASE_DIR, 'campaigns')
FIRMWARE_DIR = os.path.join(BASE_DIR, 'firmware')
CERT_DIR = os.path.join(BASE_DIR, 'certs')

# Create directories
os.makedirs(CAMPAIGNS_DIR, exist_ok=True)
os.makedirs(FIRMWARE_DIR, exist_ok=True)

# Server configuration
SERVER_URL = os.getenv('SERVER_URL', 'https://ota-cdn.oem-server.com')
MQTT_BROKER_HOST = os.getenv('MQTT_BROKER_HOST', 'localhost')
MQTT_BROKER_PORT = int(os.getenv('MQTT_BROKER_PORT', '1883'))

# ==================== Global State ====================

# Campaign database (in production, use PostgreSQL/MongoDB)
campaigns_db: Dict[str, Dict] = {}

# Vehicle database
vehicles_db: Dict[str, Dict] = {}

# MQTT Broker
mqtt_broker: Optional[OTAMQTTBroker] = None


# ==================== Campaign Management ====================

class CampaignManager:
    """OTA Campaign Manager"""
    
    @staticmethod
    def create_campaign(campaign_id: str, campaign_data: Dict) -> Dict:
        """Create new OTA campaign"""
        campaign = {
            'campaign_id': campaign_id,
            'created_at': datetime.now().isoformat(),
            'status': 'created',
            'target_ecus': campaign_data.get('target_ecus', []),
            'total_size_mb': campaign_data.get('total_size_mb', 0),
            'priority': campaign_data.get('priority', 'normal'),
            'rollback_enabled': campaign_data.get('rollback_enabled', True),
            'estimated_duration_minutes': campaign_data.get('estimated_duration_minutes', 30),
            'packages': campaign_data.get('packages', []),
            'campaign_dir': os.path.join(CAMPAIGNS_DIR, f'Campaign_{campaign_id}'),
            'deployment_status': {}
        }
        
        campaigns_db[campaign_id] = campaign
        return campaign
    
    @staticmethod
    def get_campaign(campaign_id: str) -> Optional[Dict]:
        """Get campaign by ID"""
        return campaigns_db.get(campaign_id)
    
    @staticmethod
    def list_campaigns() -> List[Dict]:
        """List all campaigns"""
        return list(campaigns_db.values())
    
    @staticmethod
    def get_campaign_package_path(campaign_id: str) -> Optional[str]:
        """Get path to campaign full package"""
        campaign = campaigns_db.get(campaign_id)
        if not campaign:
            return None
        
        # Look for full_package.bin in campaign directory
        campaign_dir = campaign['campaign_dir']
        full_package_path = os.path.join(campaign_dir, 'full_package.bin')
        
        if os.path.exists(full_package_path):
            return full_package_path
        
        return None
    
    @staticmethod
    def deploy_campaign_to_vehicle(campaign_id: str, vin: str) -> bool:
        """Deploy campaign to specific vehicle"""
        campaign = campaigns_db.get(campaign_id)
        if not campaign:
            return False
        
        if not mqtt_broker or not mqtt_broker.is_vehicle_online(vin):
            return False
        
        # Send campaign notification
        mqtt_broker.send_campaign_notification(vin, campaign)
        
        # Update deployment status
        if 'deployment_status' not in campaign:
            campaign['deployment_status'] = {}
        
        campaign['deployment_status'][vin] = {
            'status': 'notified',
            'notified_at': datetime.now().isoformat()
        }
        
        return True


# ==================== MQTT Message Handlers ====================

def setup_mqtt_handlers():
    """Setup MQTT message handlers"""
    
    def on_wake_up(vin: str, payload: Dict):
        """Handle vehicle wake-up"""
        print(f"[{vin}] Vehicle woke up: {payload.get('event', 'unknown')}")
        
        # Update vehicle database
        vehicles_db[vin] = {
            'vin': vin,
            'last_wake_up': datetime.now().isoformat(),
            'vmg_info': payload.get('vmg_info', {}),
            'vehicle_state': payload.get('vehicle_state', {}),
            'status': 'online'
        }
        
        # Auto-request VCI
        if mqtt_broker:
            mqtt_broker.request_vci(vin)
    
    def on_vci_report(vin: str, payload: Dict):
        """Handle VCI report"""
        print(f"[{vin}] VCI Report received")
        
        if vin in vehicles_db:
            vehicles_db[vin]['vci'] = payload
            vehicles_db[vin]['last_vci_update'] = datetime.now().isoformat()
    
    def on_ota_readiness_response(vin: str, payload: Dict):
        """Handle OTA readiness response"""
        status = payload.get('overall_status', 'unknown')
        print(f"[{vin}] OTA Readiness: {status}")
        
        if vin in vehicles_db:
            vehicles_db[vin]['ota_readiness'] = payload
    
    def on_campaign_response(vin: str, payload: Dict):
        """Handle campaign acceptance/rejection"""
        campaign_id = payload.get('campaign_id')
        status = payload.get('status', 'unknown')
        
        print(f"[{vin}] Campaign {campaign_id} response: {status}")
        
        if campaign_id in campaigns_db:
            campaign = campaigns_db[campaign_id]
            if 'deployment_status' not in campaign:
                campaign['deployment_status'] = {}
            
            campaign['deployment_status'][vin]['status'] = status
            campaign['deployment_status'][vin]['response_at'] = datetime.now().isoformat()
            
            # If accepted, send metadata with download URL
            if status == 'accepted' and mqtt_broker:
                send_campaign_metadata_to_vehicle(campaign_id, vin)
    
    def on_download_progress(vin: str, payload: Dict):
        """Handle download progress"""
        campaign_id = payload.get('campaign_id')
        progress = payload.get('progress', {})
        percentage = progress.get('percentage', 0)
        
        print(f"[{vin}] Download progress: {percentage:.1f}%")
    
    def on_download_complete(vin: str, payload: Dict):
        """Handle download complete"""
        campaign_id = payload.get('campaign_id')
        status = payload.get('status')
        
        print(f"[{vin}] Download complete: {status}")
        
        if campaign_id in campaigns_db:
            campaign = campaigns_db[campaign_id]
            if 'deployment_status' in campaign and vin in campaign['deployment_status']:
                campaign['deployment_status'][vin]['download_status'] = status
                campaign['deployment_status'][vin]['download_complete_at'] = datetime.now().isoformat()
    
    def on_installation_complete(vin: str, payload: Dict):
        """Handle installation complete"""
        campaign_id = payload.get('campaign_id')
        overall_status = payload.get('overall_status')
        
        print(f"[{vin}] Installation complete: {overall_status}")
        
        if campaign_id in campaigns_db:
            campaign = campaigns_db[campaign_id]
            if 'deployment_status' in campaign and vin in campaign['deployment_status']:
                campaign['deployment_status'][vin]['installation_status'] = overall_status
                campaign['deployment_status'][vin]['installation_complete_at'] = datetime.now().isoformat()
    
    def on_verification_complete(vin: str, payload: Dict):
        """Handle verification complete"""
        campaign_id = payload.get('campaign_id')
        verification_status = payload.get('verification_status')
        
        print(f"[{vin}] Verification complete: {verification_status}")
        
        if campaign_id in campaigns_db:
            campaign = campaigns_db[campaign_id]
            if 'deployment_status' in campaign and vin in campaign['deployment_status']:
                campaign['deployment_status'][vin]['verification_status'] = verification_status
                campaign['deployment_status'][vin]['verification_complete_at'] = datetime.now().isoformat()
                campaign['deployment_status'][vin]['status'] = 'completed'
    
    def on_ota_error(vin: str, payload: Dict):
        """Handle OTA error"""
        campaign_id = payload.get('campaign_id')
        error = payload.get('error', {})
        
        print(f"[{vin}] OTA Error: {error.get('message', 'Unknown error')}")
        
        if campaign_id in campaigns_db:
            campaign = campaigns_db[campaign_id]
            if 'deployment_status' in campaign and vin in campaign['deployment_status']:
                campaign['deployment_status'][vin]['error'] = error
                campaign['deployment_status'][vin]['status'] = 'error'
    
    # Register handlers
    handlers = {
        'vehicle_wake_up': on_wake_up,
        'vci_report': on_vci_report,
        'ota_readiness_response': on_ota_readiness_response,
        'ota_campaign_response': on_campaign_response,
        'ota_download_progress': on_download_progress,
        'ota_download_complete': on_download_complete,
        'ota_installation_complete': on_installation_complete,
        'ota_verification_complete': on_verification_complete,
        'ota_error': on_ota_error,
    }
    
    for msg_type, handler in handlers.items():
        mqtt_broker.register_handler(msg_type, handler)


def send_campaign_metadata_to_vehicle(campaign_id: str, vin: str):
    """Send campaign metadata with HTTPS download URL to vehicle"""
    campaign = campaigns_db.get(campaign_id)
    if not campaign or not mqtt_broker:
        return False
    
    # Generate authentication token (in production, use JWT)
    token = f"token_{vin}_{campaign_id}_{int(time.time())}"
    
    # Calculate package hash
    package_path = CampaignManager.get_campaign_package_path(campaign_id)
    if package_path and os.path.exists(package_path):
        with open(package_path, 'rb') as f:
            package_data = f.read()
            sha256 = hashlib.sha256(package_data).hexdigest()
            md5 = hashlib.md5(package_data).hexdigest()
            total_size = len(package_data)
    else:
        sha256 = "unknown"
        md5 = "unknown"
        total_size = campaign.get('total_size_mb', 0) * 1024 * 1024
    
    metadata = {
        'campaign_id': campaign_id,
        'download_session': {
            'session_id': f"dl-{int(time.time())}",
            'method': 'https',
            'protocol': 'HTTPS/1.1',
            'transport': 'Hybrid PQC-TLS 1.3',
            'cipher_suite': 'TLS_MLKEM768_X25519_WITH_AES_256_GCM_SHA384',
            'compression': 'none',
            'server_url': SERVER_URL,
            'download_endpoint': f'/packages/{campaign_id}/full_package.bin',
            'authentication': {
                'type': 'bearer_token',
                'token_expiry_sec': 3600,
                'token': token
            },
            'resume_supported': True,
            'partial_download_supported': True
        },
        'full_package': {
            'package_url': f"{SERVER_URL}/packages/{campaign_id}/full_package.bin",
            'package_id': f"full-ota-{campaign_id}",
            'total_size_bytes': total_size,
            'sha256': sha256,
            'md5': md5,
            'signature': {
                'algorithm': 'RSA-2048-SHA256',
                'public_key_id': 'oem-signing-key-2025',
                'signature_base64': 'BASE64_SIGNATURE...'
            }
        },
        'packages': campaign.get('packages', []),
        'installation_sequence': [pkg['package_id'] for pkg in campaign.get('packages', [])],
        'rollback_data': {
            'rollback_enabled': campaign.get('rollback_enabled', True),
            'rollback_timeout_sec': 300,
            'auto_rollback_on_failure': True
        }
    }
    
    mqtt_broker.send_campaign_metadata(vin, metadata)
    return True


# ==================== REST API Endpoints ====================

@app.route('/')
def index():
    """Server information"""
    return jsonify({
        'server': 'PQC OTA Server - OEM Cloud',
        'version': '1.0.0',
        'architecture': 'Zonal E/E',
        'security': {
            'transport': 'Hybrid PQC-TLS 1.3',
            'key_exchange': 'ML-KEM 768 + X25519',
            'encryption': 'AES-256-GCM',
            'hash': 'SHA-384'
        },
        'protocols': {
            'mqtt': f'{MQTT_BROKER_HOST}:{MQTT_BROKER_PORT}',
            'https': SERVER_URL
        },
        'mqtt_connected': mqtt_broker.connected if mqtt_broker else False
    })


@app.route('/health')
def health():
    """Health check"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'campaigns_count': len(campaigns_db),
        'vehicles_online': len(mqtt_broker.get_connected_vehicles()) if mqtt_broker else 0
    })


# ==================== Campaign Management API ====================

@app.route('/api/campaigns', methods=['GET'])
def list_campaigns():
    """List all campaigns"""
    return jsonify({
        'campaigns': CampaignManager.list_campaigns()
    })


@app.route('/api/campaigns/<campaign_id>', methods=['GET'])
def get_campaign(campaign_id: str):
    """Get campaign details"""
    campaign = CampaignManager.get_campaign(campaign_id)
    if campaign:
        return jsonify(campaign)
    else:
        return jsonify({'error': 'Campaign not found'}), 404


@app.route('/api/campaigns', methods=['POST'])
def create_campaign():
    """Create new campaign"""
    data = request.get_json()
    campaign_id = data.get('campaign_id')
    
    if not campaign_id:
        return jsonify({'error': 'campaign_id required'}), 400
    
    if campaign_id in campaigns_db:
        return jsonify({'error': 'Campaign already exists'}), 409
    
    campaign = CampaignManager.create_campaign(campaign_id, data)
    return jsonify(campaign), 201


@app.route('/api/campaigns/<campaign_id>/deploy/<vin>', methods=['POST'])
def deploy_campaign(campaign_id: str, vin: str):
    """Deploy campaign to specific vehicle"""
    success = CampaignManager.deploy_campaign_to_vehicle(campaign_id, vin)
    
    if success:
        return jsonify({
            'success': True,
            'campaign_id': campaign_id,
            'vin': vin,
            'status': 'notified'
        })
    else:
        return jsonify({'error': 'Deployment failed'}), 500


# ==================== Vehicle Management API ====================

@app.route('/api/vehicles', methods=['GET'])
def list_vehicles():
    """List all vehicles"""
    return jsonify({
        'vehicles': list(vehicles_db.values())
    })


@app.route('/api/vehicles/<vin>', methods=['GET'])
def get_vehicle(vin: str):
    """Get vehicle details"""
    if vin in vehicles_db:
        return jsonify(vehicles_db[vin])
    else:
        return jsonify({'error': 'Vehicle not found'}), 404


@app.route('/api/vehicles/<vin>/vci', methods=['POST'])
def request_vci(vin: str):
    """Request VCI from vehicle"""
    if not mqtt_broker:
        return jsonify({'error': 'MQTT broker not connected'}), 503
    
    if not mqtt_broker.is_vehicle_online(vin):
        return jsonify({'error': 'Vehicle not online'}), 404
    
    mqtt_broker.request_vci(vin)
    return jsonify({
        'success': True,
        'vin': vin,
        'status': 'vci_requested'
    })


@app.route('/api/vehicles/<vin>/readiness', methods=['POST'])
def check_ota_readiness(vin: str):
    """Check OTA readiness"""
    if not mqtt_broker:
        return jsonify({'error': 'MQTT broker not connected'}), 503
    
    if not mqtt_broker.is_vehicle_online(vin):
        return jsonify({'error': 'Vehicle not online'}), 404
    
    data = request.get_json() or {}
    target_ecus = data.get('target_ecus', ['VMG', 'ZGW', 'ECU_011', 'ECU_012'])
    
    mqtt_broker.request_ota_readiness(vin, target_ecus)
    return jsonify({
        'success': True,
        'vin': vin,
        'status': 'readiness_check_requested'
    })


# ==================== HTTPS Package Download API ====================

@app.route('/packages/<campaign_id>/full_package.bin', methods=['GET'])
def download_campaign_package(campaign_id: str):
    """Download full OTA package (with Range support for resume)"""
    # Verify authentication token
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Unauthorized'}), 401
    
    # Get package path
    package_path = CampaignManager.get_campaign_package_path(campaign_id)
    if not package_path or not os.path.exists(package_path):
        return jsonify({'error': 'Package not found'}), 404
    
    # Check if Range header is present (for resume support)
    range_header = request.headers.get('Range')
    
    if range_header:
        # Parse Range header (e.g., "bytes=0-1023")
        try:
            byte_range = range_header.replace('bytes=', '').split('-')
            start = int(byte_range[0]) if byte_range[0] else 0
            
            file_size = os.path.getsize(package_path)
            end = int(byte_range[1]) if byte_range[1] else file_size - 1
            
            # Read partial file
            with open(package_path, 'rb') as f:
                f.seek(start)
                data = f.read(end - start + 1)
            
            # Return 206 Partial Content
            response = Response(data, 206)
            response.headers['Content-Range'] = f'bytes {start}-{end}/{file_size}'
            response.headers['Content-Length'] = str(len(data))
            response.headers['Accept-Ranges'] = 'bytes'
            return response
        
        except Exception as e:
            print(f"Range request error: {e}")
            return jsonify({'error': 'Invalid range request'}), 400
    
    else:
        # Full file download
        return send_file(
            package_path,
            as_attachment=True,
            download_name=f'{campaign_id}_full_package.bin'
        )


@app.route('/packages/<campaign_id>/metadata.json', methods=['GET'])
def get_campaign_metadata(campaign_id: str):
    """Get campaign metadata"""
    campaign = CampaignManager.get_campaign(campaign_id)
    if not campaign:
        return jsonify({'error': 'Campaign not found'}), 404
    
    # Load campaign_metadata.json from campaign directory
    metadata_path = os.path.join(campaign['campaign_dir'], 'campaign_metadata.json')
    if os.path.exists(metadata_path):
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
        return jsonify(metadata)
    else:
        return jsonify({'error': 'Metadata not found'}), 404


# ==================== Main ====================

def init_mqtt_broker():
    """Initialize MQTT broker"""
    global mqtt_broker
    
    mqtt_broker = OTAMQTTBroker(
        broker_host=MQTT_BROKER_HOST,
        broker_port=MQTT_BROKER_PORT,
        use_tls=False  # Set to True for PQC-TLS
    )
    
    setup_mqtt_handlers()
    
    if mqtt_broker.connect():
        print(f"[MQTT] Connected to broker at {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT}")
    else:
        print("[MQTT] Failed to connect to broker")


def load_campaigns():
    """Load campaigns from disk"""
    if not os.path.exists(CAMPAIGNS_DIR):
        return
    
    for campaign_folder in os.listdir(CAMPAIGNS_DIR):
        if not campaign_folder.startswith('Campaign_'):
            continue
        
        campaign_dir = os.path.join(CAMPAIGNS_DIR, campaign_folder)
        metadata_path = os.path.join(campaign_dir, 'campaign_metadata.json')
        
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, 'r') as f:
                    metadata = json.load(f)
                
                campaign_id = metadata['campaign_id']
                campaigns_db[campaign_id] = {
                    'campaign_id': campaign_id,
                    'created_at': metadata.get('created_at', ''),
                    'status': 'ready',
                    'packages': metadata.get('packages', []),
                    'campaign_dir': campaign_dir,
                    'deployment_status': {}
                }
                
                print(f"[Campaign] Loaded: {campaign_id}")
            except Exception as e:
                print(f"[Campaign] Failed to load {campaign_folder}: {e}")


if __name__ == '__main__':
    print("╔════════════════════════════════════════════════════════════╗")
    print("║        PQC OTA Server - OEM Cloud                         ║")
    print("║        Zonal E/E Architecture                              ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print()
    
    # Initialize MQTT broker
    init_mqtt_broker()
    
    # Load existing campaigns
    load_campaigns()
    
    print(f"[Flask] Starting HTTPS server on port 5000...")
    print(f"[Flask] Server URL: {SERVER_URL}")
    print()
    
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True
    )

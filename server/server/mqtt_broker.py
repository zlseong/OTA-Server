"""
MQTT Broker Interface for OTA Server
Handles communication with VMG (Vehicle Master Gateway)
"""

import paho.mqtt.client as mqtt
import json
import threading
import time
from datetime import datetime
from typing import Dict, Callable, Optional, List
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OTAMQTTBroker:
    """
    MQTT Broker for OTA Server
    Handles VMG communication following MQTT_API_SPECIFICATION.md
    """
    
    def __init__(self, broker_host="localhost", broker_port=1883, use_tls=False):
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.use_tls = use_tls
        
        # MQTT Client
        self.client = mqtt.Client(client_id="OEM_OTA_Server", protocol=mqtt.MQTTv5)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect
        
        # Connected vehicles
        self.connected_vehicles: Dict[str, Dict] = {}
        
        # Message handlers
        self.handlers = {
            'vehicle_wake_up': [],
            'vci_report': [],
            'ota_readiness_response': [],
            'ota_campaign_response': [],
            'ota_download_progress': [],
            'ota_download_complete': [],
            'ota_download_failed': [],
            'ota_installation_start': [],
            'ota_installation_progress': [],
            'ota_installation_complete': [],
            'ota_verification_complete': [],
            'ota_error': [],
        }
        
        # Connection status
        self.connected = False
    
    def connect(self):
        """Connect to MQTT broker"""
        try:
            if self.use_tls:
                # TODO: Configure TLS with PQC certificates
                self.client.tls_set()
            
            logger.info(f"Connecting to MQTT broker at {self.broker_host}:{self.broker_port}...")
            self.client.connect(self.broker_host, self.broker_port, keepalive=60)
            self.client.loop_start()
            
            # Wait for connection
            for _ in range(10):
                if self.connected:
                    logger.info("Successfully connected to MQTT broker")
                    return True
                time.sleep(0.5)
            
            logger.error("Failed to connect to MQTT broker")
            return False
            
        except Exception as e:
            logger.error(f"MQTT connection error: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from MQTT broker"""
        logger.info("Disconnecting from MQTT broker...")
        self.client.loop_stop()
        self.client.disconnect()
        self.connected = False
    
    def _on_connect(self, client, userdata, flags, rc, properties=None):
        """Callback when connected to broker"""
        if rc == 0:
            self.connected = True
            logger.info("Connected to MQTT broker")
            
            # Subscribe to all OEM topics
            topics = [
                ("oem/+/wake_up", 1),
                ("oem/+/response", 1),
                ("oem/+/vci", 1),
                ("oem/+/telemetry", 0),
                ("oem/+/ota/status", 1),
            ]
            
            for topic, qos in topics:
                self.client.subscribe(topic, qos)
                logger.info(f"Subscribed to: {topic} (QoS {qos})")
        else:
            logger.error(f"Connection failed with code {rc}")
    
    def _on_disconnect(self, client, userdata, rc):
        """Callback when disconnected from broker"""
        self.connected = False
        logger.warning(f"Disconnected from MQTT broker (rc={rc})")
    
    def _on_message(self, client, userdata, msg):
        """Callback when message received"""
        try:
            # Parse topic
            topic_parts = msg.topic.split('/')
            if len(topic_parts) < 3:
                logger.warning(f"Invalid topic format: {msg.topic}")
                return
            
            vin = topic_parts[1]  # oem/{vin}/...
            
            # Decode payload
            payload = json.loads(msg.payload.decode('utf-8'))
            msg_type = payload.get('msg_type', 'unknown')
            
            logger.info(f"[{vin}] Received: {msg_type} on {msg.topic}")
            
            # Update vehicle status
            if vin not in self.connected_vehicles:
                self.connected_vehicles[vin] = {
                    'vin': vin,
                    'last_seen': datetime.now().isoformat(),
                    'status': 'online'
                }
            
            self.connected_vehicles[vin]['last_seen'] = datetime.now().isoformat()
            
            # Route to handlers
            if msg_type in self.handlers:
                for handler in self.handlers[msg_type]:
                    try:
                        handler(vin, payload)
                    except Exception as e:
                        logger.error(f"Handler error for {msg_type}: {e}")
            else:
                logger.warning(f"No handler for message type: {msg_type}")
        
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
        except Exception as e:
            logger.error(f"Message handling error: {e}")
    
    def register_handler(self, msg_type: str, handler: Callable):
        """Register message handler"""
        if msg_type in self.handlers:
            self.handlers[msg_type].append(handler)
            logger.info(f"Registered handler for: {msg_type}")
        else:
            logger.warning(f"Unknown message type: {msg_type}")
    
    def publish(self, vin: str, topic_suffix: str, payload: Dict, qos: int = 1):
        """
        Publish message to vehicle
        
        Args:
            vin: Vehicle VIN
            topic_suffix: Topic suffix (e.g., 'command', 'ota/campaign')
            payload: Message payload
            qos: Quality of Service (0, 1, 2)
        """
        topic = f"oem/{vin}/{topic_suffix}"
        payload_json = json.dumps(payload)
        
        result = self.client.publish(topic, payload_json, qos=qos)
        
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            logger.info(f"[{vin}] Published to {topic}: {payload.get('msg_type', 'unknown')}")
        else:
            logger.error(f"[{vin}] Failed to publish to {topic}")
        
        return result
    
    # ==================== High-level API ====================
    
    def request_vci(self, vin: str, include_zones: List[str] = None, timeout_sec: int = 30):
        """Request Vehicle Configuration Information"""
        if include_zones is None:
            include_zones = ["zone1", "zone2"]
        
        payload = {
            "msg_type": "request_vci",
            "timestamp": datetime.now().isoformat(),
            "request_id": f"vci-req-{int(time.time())}",
            "scope": {
                "include_vmg": True,
                "include_zone_gateway": True,
                "include_zone_ecus": True,
                "detailed_info": True,
                "target_zones": include_zones
            },
            "timeout_sec": timeout_sec
        }
        
        return self.publish(vin, "command", payload, qos=1)
    
    def request_ota_readiness(self, vin: str, target_ecus: List[str]):
        """Request OTA readiness check"""
        payload = {
            "msg_type": "request_ota_readiness",
            "timestamp": datetime.now().isoformat(),
            "readiness_check_id": f"ready-check-{int(time.time())}",
            "target_ecus": target_ecus,
            "conditions": [
                "vehicle_parked",
                "ignition_off",
                "battery_soc_gt_50",
                "network_quality_gt_70",
                "storage_available_gt_10gb",
                "no_critical_dtc"
            ]
        }
        
        return self.publish(vin, "command", payload, qos=1)
    
    def send_campaign_notification(self, vin: str, campaign_data: Dict):
        """Send OTA campaign notification"""
        payload = {
            "msg_type": "ota_campaign",
            "timestamp": datetime.now().isoformat(),
            "campaign_id": campaign_data['campaign_id'],
            "campaign_type": "software_update",
            "priority": campaign_data.get('priority', 'normal'),
            "vehicle": {
                "vin": vin
            },
            "target_ecus": campaign_data['target_ecus'],
            "total_size_mb": campaign_data.get('total_size_mb', 0),
            "schedule": campaign_data.get('schedule', {
                "type": "user_consent_required",
                "conditions": ["vehicle_parked", "battery_level_gt_50", "ignition_off"]
            }),
            "rollback_enabled": campaign_data.get('rollback_enabled', True),
            "estimated_duration_minutes": campaign_data.get('estimated_duration_minutes', 30),
            "release_notes_url": campaign_data.get('release_notes_url', '')
        }
        
        return self.publish(vin, "ota/campaign", payload, qos=2)
    
    def send_campaign_metadata(self, vin: str, metadata: Dict):
        """Send OTA campaign metadata with HTTPS download URL"""
        payload = {
            "msg_type": "ota_campaign_metadata",
            "timestamp": datetime.now().isoformat(),
            "campaign_id": metadata['campaign_id'],
            "download_session": metadata['download_session'],
            "full_package": metadata['full_package'],
            "packages": metadata['packages'],
            "installation_sequence": metadata.get('installation_sequence', []),
            "rollback_data": metadata.get('rollback_data', {
                "rollback_enabled": True,
                "rollback_timeout_sec": 300,
                "auto_rollback_on_failure": True
            })
        }
        
        return self.publish(vin, "ota/metadata", payload, qos=2)
    
    def get_connected_vehicles(self) -> Dict[str, Dict]:
        """Get list of connected vehicles"""
        return self.connected_vehicles.copy()
    
    def is_vehicle_online(self, vin: str) -> bool:
        """Check if vehicle is online"""
        if vin not in self.connected_vehicles:
            return False
        
        vehicle = self.connected_vehicles[vin]
        last_seen = datetime.fromisoformat(vehicle['last_seen'])
        elapsed = (datetime.now() - last_seen).total_seconds()
        
        # Consider offline if not seen for > 5 minutes
        return elapsed < 300


# ==================== Example Usage ====================

def example_handlers():
    """Example message handlers"""
    
    def on_wake_up(vin: str, payload: Dict):
        logger.info(f"[{vin}] Vehicle woke up: {payload.get('event', 'unknown')}")
        logger.info(f"[{vin}] VMG Version: {payload.get('vmg_info', {}).get('fw_version', 'unknown')}")
    
    def on_vci_report(vin: str, payload: Dict):
        logger.info(f"[{vin}] VCI Report received")
        logger.info(f"[{vin}] Total ECUs: {payload.get('collection_summary', {}).get('total_ecus', 0)}")
    
    def on_ota_readiness_response(vin: str, payload: Dict):
        status = payload.get('overall_status', 'unknown')
        logger.info(f"[{vin}] OTA Readiness: {status}")
    
    def on_ota_download_complete(vin: str, payload: Dict):
        logger.info(f"[{vin}] Download complete!")
        ready = payload.get('ready_for_installation', False)
        logger.info(f"[{vin}] Ready for installation: {ready}")
    
    def on_ota_verification_complete(vin: str, payload: Dict):
        status = payload.get('verification_status', 'unknown')
        logger.info(f"[{vin}] Verification complete: {status}")
    
    return {
        'vehicle_wake_up': on_wake_up,
        'vci_report': on_vci_report,
        'ota_readiness_response': on_ota_readiness_response,
        'ota_download_complete': on_ota_download_complete,
        'ota_verification_complete': on_ota_verification_complete,
    }


if __name__ == "__main__":
    # Test MQTT broker
    broker = OTAMQTTBroker(broker_host="localhost", broker_port=1883)
    
    # Register handlers
    handlers = example_handlers()
    for msg_type, handler in handlers.items():
        broker.register_handler(msg_type, handler)
    
    # Connect
    if broker.connect():
        logger.info("MQTT Broker ready. Press Ctrl+C to exit.")
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            broker.disconnect()
    else:
        logger.error("Failed to start MQTT broker")


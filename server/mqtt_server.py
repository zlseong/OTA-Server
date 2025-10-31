"""
MQTT Server for OTA System
Handles vehicle telemetry, control messages, and diagnostics
"""

import asyncio
import json
import logging
from typing import Dict, Callable, Optional
from datetime import datetime
import aiomqtt
from dataclasses import dataclass

from server.pqc_manager import get_pqc_manager

logger = logging.getLogger(__name__)


@dataclass
class MQTTMessage:
    """MQTT Message"""
    topic: str
    payload: dict
    qos: int
    timestamp: datetime


class MQTTServer:
    """
    MQTT Server for OTA System
    
    Features:
        - Vehicle telemetry collection
        - Remote command & control
        - Diagnostic message routing
        - OTA status reporting
    """
    
    def __init__(self, config: dict):
        """
        Initialize MQTT Server
        
        Args:
            config: MQTT configuration from server.yaml
        """
        self.config = config
        self.host = config['host']
        self.port = config.get('secure_port', 8883) if config.get('use_tls') else config['port']
        self.use_tls = config.get('use_tls', True)
        self.qos = config.get('qos', 1)
        
        # Topic subscriptions
        self.topics = config.get('topics', {})
        
        # Message handlers
        self.handlers: Dict[str, Callable] = {}
        
        # PQC-TLS support
        self.pqc_manager = get_pqc_manager() if self.use_tls else None
        
        # Statistics
        self.stats = {
            'messages_received': 0,
            'messages_sent': 0,
            'errors': 0
        }
    
    async def start(self):
        """Start MQTT server"""
        logger.info(f"Starting MQTT server on {self.host}:{self.port}")
        logger.info(f"TLS enabled: {self.use_tls}")
        
        # Register default handlers
        self._register_default_handlers()
        
        # Create SSL context if TLS enabled
        tls_context = None
        if self.use_tls:
            pqc_config_id = self.config.get('pqc_config_id', 2)
            cert_paths = self.pqc_manager.get_cert_paths(pqc_config_id)
            
            tls_context = self.pqc_manager.create_ssl_context(
                config_id=pqc_config_id,
                cert_file=cert_paths['cert'],
                key_file=cert_paths['key'],
                ca_file=cert_paths['ca'],
                server_side=True
            )
        
        # Connect to MQTT broker (using aiomqtt)
        try:
            async with aiomqtt.Client(
                hostname=self.host,
                port=self.port,
                tls_context=tls_context,
                keepalive=self.config.get('keepalive', 60)
            ) as client:
                
                # Subscribe to topics
                await self._subscribe_topics(client)
                
                logger.info("MQTT server started successfully")
                
                # Message loop
                async for message in client.messages:
                    await self._handle_message(message)
        
        except Exception as e:
            logger.error(f"MQTT server error: {e}")
            raise
    
    async def _subscribe_topics(self, client):
        """Subscribe to configured topics"""
        for topic_name, topic_pattern in self.topics.items():
            await client.subscribe(topic_pattern, qos=self.qos)
            logger.info(f"Subscribed to {topic_name}: {topic_pattern}")
    
    async def _handle_message(self, message):
        """
        Handle incoming MQTT message
        
        Args:
            message: MQTT message
        """
        try:
            # Parse payload
            payload = json.loads(message.payload.decode())
            
            # Create message object
            mqtt_msg = MQTTMessage(
                topic=str(message.topic),
                payload=payload,
                qos=message.qos,
                timestamp=datetime.now()
            )
            
            logger.debug(f"Received message on {mqtt_msg.topic}")
            
            # Route to appropriate handler
            await self._route_message(mqtt_msg)
            
            self.stats['messages_received'] += 1
            
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON payload on {message.topic}")
            self.stats['errors'] += 1
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            self.stats['errors'] += 1
    
    async def _route_message(self, message: MQTTMessage):
        """
        Route message to appropriate handler
        
        Args:
            message: Parsed MQTT message
        """
        topic = message.topic
        
        # Determine message type from topic
        if 'telemetry' in topic:
            await self._handle_telemetry(message)
        elif 'control' in topic:
            await self._handle_control(message)
        elif 'diagnostics' in topic:
            await self._handle_diagnostics(message)
        elif 'ota/status' in topic:
            await self._handle_ota_status(message)
        else:
            # Check custom handlers
            for pattern, handler in self.handlers.items():
                if pattern in topic:
                    await handler(message)
                    return
            
            logger.warning(f"No handler for topic: {topic}")
    
    async def _handle_telemetry(self, message: MQTTMessage):
        """
        Handle vehicle telemetry message
        
        Message format:
        {
            "message_type": "TELEMETRY",
            "vehicle_id": "VMG-001",
            "data": {
                "battery_soc": 85.5,
                "speed": 60.0,
                "temperature": 25.0
            }
        }
        """
        payload = message.payload
        vehicle_id = payload.get('vehicle_id')
        
        logger.info(f"Telemetry from {vehicle_id}")
        
        # Store telemetry data (implement based on requirements)
        # await self.db.store_telemetry(vehicle_id, payload['data'])
    
    async def _handle_control(self, message: MQTTMessage):
        """
        Handle control message
        
        Message format:
        {
            "message_type": "CONTROL_COMMAND",
            "vehicle_id": "VMG-001",
            "command": "START_OTA_UPDATE",
            "parameters": {...}
        }
        """
        payload = message.payload
        vehicle_id = payload.get('vehicle_id')
        command = payload.get('command')
        
        logger.info(f"Control command '{command}' for {vehicle_id}")
        
        # Process control command
        # await self.process_control_command(vehicle_id, command, payload.get('parameters'))
    
    async def _handle_diagnostics(self, message: MQTTMessage):
        """
        Handle diagnostic message
        
        Message format:
        {
            "message_type": "DIAGNOSTIC_RESPONSE",
            "vehicle_id": "VMG-001",
            "ecu_id": "ECU_001",
            "service_id": "0x22",
            "response_data": "..."
        }
        """
        payload = message.payload
        vehicle_id = payload.get('vehicle_id')
        ecu_id = payload.get('ecu_id')
        
        logger.info(f"Diagnostic response from {vehicle_id}/{ecu_id}")
        
        # Store diagnostic result
        # await self.db.store_diagnostic_result(payload)
    
    async def _handle_ota_status(self, message: MQTTMessage):
        """
        Handle OTA status update
        
        Message format:
        {
            "message_type": "OTA_STATUS_UPDATE",
            "vehicle_id": "VMG-001",
            "update_id": "update-123",
            "status": "in_progress",
            "progress": 45,
            "ecus_completed": ["ECU_001", "ECU_002"]
        }
        """
        payload = message.payload
        vehicle_id = payload.get('vehicle_id')
        update_id = payload.get('update_id')
        status = payload.get('status')
        progress = payload.get('progress', 0)
        
        logger.info(f"OTA status from {vehicle_id}: {update_id} - {status} ({progress}%)")
        
        # Update OTA status in database
        # await self.db.update_ota_status(update_id, status, progress)
    
    async def publish(self, topic: str, payload: dict, qos: Optional[int] = None):
        """
        Publish message to MQTT topic
        
        Args:
            topic: MQTT topic
            payload: Message payload (will be JSON serialized)
            qos: Quality of Service level
        """
        if qos is None:
            qos = self.qos
        
        try:
            message = json.dumps(payload)
            
            # TODO: Implement publish (requires maintaining client connection)
            logger.info(f"Publishing to {topic}: {message[:100]}...")
            
            self.stats['messages_sent'] += 1
            
        except Exception as e:
            logger.error(f"Failed to publish message: {e}")
            self.stats['errors'] += 1
    
    async def send_control_command(self, vehicle_id: str, command: str, parameters: dict = None):
        """
        Send control command to vehicle
        
        Args:
            vehicle_id: Target vehicle ID
            command: Command name
            parameters: Command parameters
        """
        topic = f"vehicle/{vehicle_id}/control"
        
        payload = {
            "message_type": "CONTROL_COMMAND",
            "message_id": f"cmd-{datetime.now().timestamp()}",
            "timestamp": datetime.now().isoformat(),
            "vehicle_id": vehicle_id,
            "command": command,
            "parameters": parameters or {}
        }
        
        await self.publish(topic, payload)
    
    async def send_diagnostic_request(self, vehicle_id: str, ecu_id: str, 
                                     service_id: str, data: bytes = None):
        """
        Send diagnostic request to vehicle
        
        Args:
            vehicle_id: Target vehicle ID
            ecu_id: Target ECU ID
            service_id: UDS service ID (e.g., "0x22")
            data: Additional diagnostic data
        """
        topic = f"vehicle/{vehicle_id}/diagnostics"
        
        payload = {
            "message_type": "DIAGNOSTIC_REQUEST",
            "message_id": f"diag-{datetime.now().timestamp()}",
            "timestamp": datetime.now().isoformat(),
            "vehicle_id": vehicle_id,
            "ecu_id": ecu_id,
            "service_id": service_id,
            "data": data.hex() if data else None
        }
        
        await self.publish(topic, payload)
    
    def register_handler(self, topic_pattern: str, handler: Callable):
        """
        Register custom message handler
        
        Args:
            topic_pattern: Topic pattern to match
            handler: Async callback function
        """
        self.handlers[topic_pattern] = handler
        logger.info(f"Registered handler for pattern: {topic_pattern}")
    
    def _register_default_handlers(self):
        """Register default message handlers"""
        # Add any default handlers here
        pass
    
    def get_statistics(self) -> dict:
        """Get server statistics"""
        return {
            **self.stats,
            'uptime': None,  # TODO: Calculate uptime
            'active_connections': None  # TODO: Track connections
        }


# Convenience function
async def start_mqtt_server(config: dict):
    """
    Start MQTT server
    
    Args:
        config: MQTT configuration
    """
    server = MQTTServer(config)
    await server.start()


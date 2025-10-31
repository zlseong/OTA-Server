"""
Remote Diagnostics Server
Sends UDS diagnostic messages to VMG -> Zonal Gateway -> ECU
"""

import asyncio
import logging
from typing import Dict, Optional, List
from dataclasses import dataclass
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)


@dataclass
class DiagnosticRequest:
    """Diagnostic request"""
    request_id: str
    vehicle_id: str
    zonal_gateway_id: Optional[str]
    ecu_id: str
    service_id: str  # UDS service ID (e.g., "0x22")
    data: Optional[bytes]
    timestamp: datetime
    status: str = "pending"


@dataclass
class DiagnosticResponse:
    """Diagnostic response"""
    request_id: str
    ecu_id: str
    success: bool
    response_data: Optional[bytes]
    error_code: Optional[str]
    duration_ms: int
    timestamp: datetime


class DiagnosticsServer:
    """
    Remote Diagnostics Server
    
    Features:
        - Send UDS messages to specific ECUs
        - Broadcast diagnostics to Zonal Gateway
        - Aggregate diagnostic results
        - Support ISO 14229 (UDS) services
    """
    
    def __init__(self, config: dict, db_connection, mqtt_server):
        """
        Initialize Diagnostics Server
        
        Args:
            config: Diagnostics configuration
            db_connection: Database connection pool
            mqtt_server: MQTT server instance
        """
        self.config = config
        self.db = db_connection
        self.mqtt = mqtt_server
        
        self.timeout = config.get('timeout', 30)
        self.max_retries = config.get('max_retries', 3)
        
        # Pending requests
        self.pending_requests: Dict[str, DiagnosticRequest] = {}
        self.responses: Dict[str, DiagnosticResponse] = {}
        
        # UDS Services
        self.supported_services = config.get('uds', {}).get('services', [])
    
    async def send_diagnostic(self, vehicle_id: str, ecu_id: str,
                             service_id: str, data: Optional[bytes] = None,
                             zonal_gateway_id: Optional[str] = None) -> str:
        """
        Send diagnostic message to ECU
        
        Args:
            vehicle_id: Target vehicle ID
            ecu_id: Target ECU ID
            service_id: UDS service ID (e.g., "0x22" for ReadDataByIdentifier)
            data: Additional diagnostic data
            zonal_gateway_id: Specific Zonal Gateway (optional)
            
        Returns:
            Request ID for tracking
        """
        request_id = str(uuid.uuid4())
        
        logger.info(f"Sending diagnostic: {request_id}")
        logger.info(f"  Vehicle: {vehicle_id}")
        logger.info(f"  ECU: {ecu_id}")
        logger.info(f"  Service: {service_id}")
        
        # Create request
        request = DiagnosticRequest(
            request_id=request_id,
            vehicle_id=vehicle_id,
            zonal_gateway_id=zonal_gateway_id,
            ecu_id=ecu_id,
            service_id=service_id,
            data=data,
            timestamp=datetime.now()
        )
        
        # Store request
        self.pending_requests[request_id] = request
        
        # Send via MQTT
        await self._send_via_mqtt(request)
        
        # Store in database
        await self._store_request(request)
        
        return request_id
    
    async def broadcast_diagnostic_to_zone(self, vehicle_id: str, 
                                          zonal_gateway_id: str,
                                          service_id: str,
                                          data: Optional[bytes] = None) -> str:
        """
        Broadcast diagnostic to all ECUs in a Zonal Gateway
        
        Args:
            vehicle_id: Target vehicle ID
            zonal_gateway_id: Target Zonal Gateway ID
            service_id: UDS service ID
            data: Diagnostic data
            
        Returns:
            Request ID
        """
        logger.info(f"Broadcasting diagnostic to zone: {zonal_gateway_id}")
        
        # Get all ECUs in this Zonal Gateway
        async with self.db.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT ecu_id FROM ecus e
                JOIN zonal_gateways zg ON e.zonal_gateway_id = zg.id
                WHERE zg.zg_id = $1 AND e.vehicle_id = (
                    SELECT id FROM vehicles WHERE vmg_id = $2
                )
                """,
                zonal_gateway_id, vehicle_id
            )
        
        ecu_ids = [row['ecu_id'] for row in rows]
        logger.info(f"  Target ECUs: {len(ecu_ids)}")
        
        # Send to all ECUs
        request_ids = []
        for ecu_id in ecu_ids:
            req_id = await self.send_diagnostic(
                vehicle_id, ecu_id, service_id, data, zonal_gateway_id
            )
            request_ids.append(req_id)
        
        # Return master request ID (first one)
        return request_ids[0] if request_ids else None
    
    async def get_diagnostic_result(self, request_id: str) -> Optional[DiagnosticResponse]:
        """
        Get diagnostic result
        
        Args:
            request_id: Request ID
            
        Returns:
            DiagnosticResponse or None if not ready
        """
        # Check in-memory cache first
        if request_id in self.responses:
            return self.responses[request_id]
        
        # Check database
        async with self.db.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM diagnostics
                WHERE diagnostic_id = $1
                """,
                request_id
            )
        
        if not row:
            return None
        
        response = DiagnosticResponse(
            request_id=row['diagnostic_id'],
            ecu_id=row.get('ecu_id'),
            success=row.get('success', False),
            response_data=row.get('response_data'),
            error_code=row.get('error_code'),
            duration_ms=row.get('duration_ms', 0),
            timestamp=row['received_at'] or row['sent_at']
        )
        
        return response
    
    async def wait_for_result(self, request_id: str, timeout: Optional[int] = None) -> DiagnosticResponse:
        """
        Wait for diagnostic result with timeout
        
        Args:
            request_id: Request ID
            timeout: Timeout in seconds (default from config)
            
        Returns:
            DiagnosticResponse
            
        Raises:
            TimeoutError: If timeout exceeded
        """
        timeout = timeout or self.timeout
        start_time = datetime.now()
        
        while (datetime.now() - start_time).total_seconds() < timeout:
            result = await self.get_diagnostic_result(request_id)
            if result:
                return result
            
            await asyncio.sleep(0.5)
        
        raise TimeoutError(f"Diagnostic request {request_id} timed out")
    
    async def handle_diagnostic_response(self, response_data: dict):
        """
        Handle diagnostic response from MQTT
        
        Args:
            response_data: Response data from MQTT message
        """
        request_id = response_data.get('request_id')
        ecu_id = response_data.get('ecu_id')
        
        logger.info(f"Received diagnostic response: {request_id} from {ecu_id}")
        
        # Create response object
        response = DiagnosticResponse(
            request_id=request_id,
            ecu_id=ecu_id,
            success=response_data.get('success', False),
            response_data=bytes.fromhex(response_data.get('response_data', '')),
            error_code=response_data.get('error_code'),
            duration_ms=response_data.get('duration_ms', 0),
            timestamp=datetime.now()
        )
        
        # Store response
        self.responses[request_id] = response
        
        # Update database
        await self._store_response(response)
        
        # Remove from pending
        if request_id in self.pending_requests:
            del self.pending_requests[request_id]
    
    async def _send_via_mqtt(self, request: DiagnosticRequest):
        """Send diagnostic request via MQTT"""
        topic = f"vehicle/{request.vehicle_id}/diagnostics"
        
        payload = {
            "message_type": "DIAGNOSTIC_REQUEST",
            "request_id": request.request_id,
            "timestamp": request.timestamp.isoformat(),
            "zonal_gateway_id": request.zonal_gateway_id,
            "ecu_id": request.ecu_id,
            "service_id": request.service_id,
            "data": request.data.hex() if request.data else None
        }
        
        await self.mqtt.publish(topic, payload)
    
    async def _store_request(self, request: DiagnosticRequest):
        """Store diagnostic request in database"""
        async with self.db.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO diagnostics (
                    diagnostic_id, vehicle_id, ecu_id, 
                    service_id, request_data, status, sent_at
                )
                VALUES ($1, (SELECT id FROM vehicles WHERE vmg_id = $2), 
                        (SELECT id FROM ecus WHERE ecu_id = $3),
                        $4, $5, $6, $7)
                """,
                request.request_id, request.vehicle_id, request.ecu_id,
                request.service_id, request.data, request.status, request.timestamp
            )
    
    async def _store_response(self, response: DiagnosticResponse):
        """Store diagnostic response in database"""
        async with self.db.acquire() as conn:
            await conn.execute(
                """
                UPDATE diagnostics
                SET response_data = $1, success = $2, error_code = $3,
                    duration_ms = $4, received_at = $5, status = 'completed'
                WHERE diagnostic_id = $6
                """,
                response.response_data, response.success, response.error_code,
                response.duration_ms, response.timestamp, response.request_id
            )
    
    def get_statistics(self) -> dict:
        """Get diagnostics statistics"""
        return {
            "pending_requests": len(self.pending_requests),
            "completed_responses": len(self.responses),
            "supported_services": self.supported_services
        }


# UDS Service Helpers

class UDSService:
    """UDS Service IDs (ISO 14229)"""
    DIAGNOSTIC_SESSION_CONTROL = "0x10"
    ECU_RESET = "0x11"
    READ_DATA_BY_ID = "0x22"
    READ_MEMORY_BY_ADDRESS = "0x23"
    SECURITY_ACCESS = "0x27"
    COMMUNICATION_CONTROL = "0x28"
    WRITE_DATA_BY_ID = "0x2E"
    ROUTINE_CONTROL = "0x31"
    REQUEST_DOWNLOAD = "0x34"
    TRANSFER_DATA = "0x36"
    REQUEST_TRANSFER_EXIT = "0x37"
    READ_DTC_INFORMATION = "0x19"
    CLEAR_DTC_INFORMATION = "0x14"


class UDSDataIdentifier:
    """Common UDS Data Identifiers (DIDs)"""
    VIN = "0xF190"
    HARDWARE_VERSION = "0xF191"
    SOFTWARE_VERSION = "0xF194"
    ECU_SERIAL_NUMBER = "0xF18C"
    VEHICLE_SPEED = "0x0D"
    ENGINE_RPM = "0x0C"


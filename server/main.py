"""
OTA Server Main Entry Point
Starts all services (MQTT, HTTPS, Diagnostics)
"""

import asyncio
import logging
import sys
from pathlib import Path
import yaml
import signal

from server.mqtt_server import start_mqtt_server
from server.https_server import start_https_server
from server.pqc_manager import get_pqc_manager

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('ota_server.log')
    ]
)

logger = logging.getLogger(__name__)


class OTAServer:
    """
    Main OTA Server
    
    Manages all services:
        - MQTT Server (telemetry & control)
        - HTTPS Server (firmware delivery & API)
        - Diagnostics Service
    """
    
    def __init__(self, config_file: str = "config/server.yaml"):
        """
        Initialize OTA Server
        
        Args:
            config_file: Path to configuration file
        """
        self.config = self._load_config(config_file)
        self.services = []
        self.shutdown_event = asyncio.Event()
    
    def _load_config(self, config_file: str) -> dict:
        """Load configuration from YAML file"""
        config_path = Path(config_file)
        
        if not config_path.exists():
            logger.error(f"Configuration file not found: {config_file}")
            logger.info("Using example configuration...")
            config_path = Path("config/server.yaml.example")
        
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            logger.info(f"Loaded configuration from {config_path}")
            return config
        
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            sys.exit(1)
    
    async def start(self):
        """Start all services"""
        logger.info("=" * 60)
        logger.info("OTA Server Starting")
        logger.info("=" * 60)
        logger.info(f"Environment: {self.config['server']['environment']}")
        logger.info(f"Log Level: {self.config['server']['log_level']}")
        
        # Initialize PQC Manager
        logger.info("\nInitializing PQC Manager...")
        pqc_manager = get_pqc_manager()
        configs = pqc_manager.list_configs()
        logger.info(f"  Loaded {len(configs)} PQC configurations")
        default_cfg = pqc_manager.get_config()
        logger.info(f"  Default: {default_cfg.name}")
        logger.info(f"    KEM: {default_cfg.kem_algorithm}")
        logger.info(f"    Signature: {default_cfg.sig_algorithm}")
        logger.info(f"    Security: {default_cfg.security_bits}-bit")
        
        # Setup signal handlers
        self._setup_signal_handlers()
        
        # Start services
        tasks = []
        
        # MQTT Server
        if self.config.get('mqtt', {}).get('enabled', True):
            logger.info("\nStarting MQTT Server...")
            mqtt_task = asyncio.create_task(
                start_mqtt_server(self.config['mqtt'])
            )
            tasks.append(mqtt_task)
            self.services.append('MQTT')
        
        # HTTPS Server
        if self.config.get('https', {}).get('enabled', True):
            logger.info("\nStarting HTTPS Server...")
            https_task = asyncio.create_task(
                start_https_server(self.config['https'])
            )
            tasks.append(https_task)
            self.services.append('HTTPS')
        
        logger.info("\n" + "=" * 60)
        logger.info("OTA Server Running")
        logger.info("=" * 60)
        logger.info(f"Active Services: {', '.join(self.services)}")
        logger.info("\nPress Ctrl+C to stop")
        logger.info("=" * 60 + "\n")
        
        # Wait for shutdown signal
        await self.shutdown_event.wait()
        
        # Cleanup
        logger.info("\nShutting down services...")
        for task in tasks:
            task.cancel()
        
        await asyncio.gather(*tasks, return_exceptions=True)
        
        logger.info("OTA Server stopped")
    
    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown"""
        def signal_handler(sig, frame):
            logger.info(f"\nReceived signal {sig}, shutting down...")
            self.shutdown_event.set()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)


async def main():
    """Main entry point"""
    # ASCII Banner
    banner = """
    ╔═══════════════════════════════════════════════════════════╗
    ║                                                           ║
    ║              OTA Server with PQC-Hybrid TLS               ║
    ║                                                           ║
    ║  Automotive Over-The-Air Update Server                    ║
    ║  Post-Quantum Cryptography Support                        ║
    ║  OpenSSL 3.6.0 Native PQC                                 ║
    ║                                                           ║
    ║  Features:                                                ║
    ║    - 100 ECU Version Management                           ║
    ║    - 13 PQC Configurations (ML-KEM + ML-DSA/ECDSA)        ║
    ║    - Zonal Gateway Optimized Packaging                    ║
    ║    - Remote Diagnostics (UDS over DoIP)                   ║
    ║    - MQTT + HTTPS with PQC-TLS                            ║
    ║                                                           ║
    ╚═══════════════════════════════════════════════════════════╝
    """
    
    print(banner)
    
    # Start server
    server = OTAServer()
    await server.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


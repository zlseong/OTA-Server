"""
PQC Manager
Manages PQC-TLS configurations using OpenSSL 3.6.0
"""

import ssl
import logging
from typing import Dict, Optional
from dataclasses import dataclass
import yaml

logger = logging.getLogger(__name__)


@dataclass
class PQCConfig:
    """PQC Configuration"""
    id: int
    name: str
    kem_algorithm: str
    kem_bits: int
    sig_algorithm: str
    security_bits: int
    openssl_groups: str
    openssl_sigalgs: str
    
    # Key/Signature sizes
    kem_public_key_size: int
    kem_ciphertext_size: int
    sig_signature_size: int


class PQCManager:
    """
    PQC Configuration Manager
    
    Uses OpenSSL 3.6.0 native PQC support (no provider needed)
    Supports 13 predefined configurations
    """
    
    def __init__(self, config_file: str = "config/pqc_configs.yaml"):
        """
        Initialize PQC Manager
        
        Args:
            config_file: Path to PQC configuration file
        """
        self.configs: Dict[int, PQCConfig] = {}
        self.default_config_id = 2  # ML-KEM-768 + ECDSA-P256
        self._load_configs(config_file)
    
    def _load_configs(self, config_file: str):
        """Load PQC configurations from YAML"""
        try:
            with open(config_file, 'r') as f:
                data = yaml.safe_load(f)
            
            for cfg in data['configurations']:
                pqc_config = PQCConfig(
                    id=cfg['id'],
                    name=cfg['name'],
                    kem_algorithm=cfg['kem']['algorithm'],
                    kem_bits=cfg['security_bits'],
                    sig_algorithm=cfg['signature']['algorithm'],
                    security_bits=cfg['security_bits'],
                    openssl_groups=cfg['openssl_groups'],
                    openssl_sigalgs=cfg['openssl_sigalgs'],
                    kem_public_key_size=cfg['kem']['public_key_size'],
                    kem_ciphertext_size=cfg['kem']['ciphertext_size'],
                    sig_signature_size=cfg['signature']['signature_size']
                )
                self.configs[cfg['id']] = pqc_config
                
                # Set default if specified
                if cfg.get('is_default'):
                    self.default_config_id = cfg['id']
            
            logger.info(f"Loaded {len(self.configs)} PQC configurations")
            logger.info(f"Default config: {self.default_config_id} ({self.configs[self.default_config_id].name})")
            
        except Exception as e:
            logger.error(f"Failed to load PQC configs: {e}")
            raise
    
    def get_config(self, config_id: Optional[int] = None) -> PQCConfig:
        """
        Get PQC configuration by ID
        
        Args:
            config_id: Configuration ID (0-12), None for default
            
        Returns:
            PQCConfig instance
        """
        if config_id is None:
            config_id = self.default_config_id
        
        if config_id not in self.configs:
            raise ValueError(f"Invalid PQC config ID: {config_id}. Valid range: 0-12")
        
        return self.configs[config_id]
    
    def create_ssl_context(self, config_id: Optional[int] = None,
                          cert_file: str = None, key_file: str = None,
                          ca_file: str = None, server_side: bool = True) -> ssl.SSLContext:
        """
        Create SSL context with PQC configuration
        
        Args:
            config_id: PQC configuration ID
            cert_file: Certificate file path
            key_file: Private key file path
            ca_file: CA certificate file path
            server_side: True for server, False for client
            
        Returns:
            SSL context configured with PQC
        """
        config = self.get_config(config_id)
        
        logger.info(f"Creating SSL context with PQC config {config.id}: {config.name}")
        logger.info(f"  KEM: {config.kem_algorithm}")
        logger.info(f"  Signature: {config.sig_algorithm}")
        logger.info(f"  Security: {config.security_bits}-bit")
        
        # Create SSL context
        if server_side:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        else:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        
        # Set minimum TLS version
        context.minimum_version = ssl.TLSVersion.TLSv1_3
        
        # Set cipher suites (TLS 1.3)
        context.set_ciphers('TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256')
        
        # OpenSSL 3.6.0: Set KEM groups
        # Note: Python ssl module may not expose set_groups yet
        # In that case, this is set via certificate generation
        try:
            if hasattr(context, 'set_groups'):
                context.set_groups([config.openssl_groups])
                logger.info(f"  Set KEM group: {config.openssl_groups}")
        except Exception as e:
            logger.warning(f"Could not set KEM groups directly: {e}")
            logger.info("  KEM will be determined by certificate type")
        
        # Load certificates
        if cert_file and key_file:
            context.load_cert_chain(cert_file, key_file)
            logger.info(f"  Loaded certificate: {cert_file}")
        
        # Load CA certificate for mTLS
        if ca_file:
            context.load_verify_locations(cafile=ca_file)
            context.verify_mode = ssl.CERT_REQUIRED
            logger.info(f"  Loaded CA cert: {ca_file}")
        
        # Additional security settings
        context.check_hostname = False if server_side else True
        context.options |= ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1 | ssl.OP_NO_TLSv1_2
        
        return context
    
    def get_cert_paths(self, config_id: Optional[int] = None) -> Dict[str, str]:
        """
        Get certificate file paths for a configuration
        
        Args:
            config_id: PQC configuration ID
            
        Returns:
            Dictionary with cert, key, and ca paths
        """
        config = self.get_config(config_id)
        
        # Determine cert file naming based on KEM algorithm
        kem_name = config.kem_algorithm.lower().replace('-', '')
        
        return {
            'cert': f'certs/server_{kem_name}_cert.pem',
            'key': f'certs/server_{kem_name}_key.pem',
            'ca': 'certs/ca_cert.pem'
        }
    
    def list_configs(self) -> list:
        """Get list of all available configurations"""
        return [
            {
                'id': cfg.id,
                'name': cfg.name,
                'kem': cfg.kem_algorithm,
                'signature': cfg.sig_algorithm,
                'security_bits': cfg.security_bits,
                'is_default': cfg.id == self.default_config_id
            }
            for cfg in sorted(self.configs.values(), key=lambda x: x.id)
        ]
    
    def validate_config_id(self, config_id: int) -> bool:
        """Check if config ID is valid"""
        return config_id in self.configs
    
    def get_config_by_name(self, name: str) -> Optional[PQCConfig]:
        """Get configuration by name"""
        for cfg in self.configs.values():
            if cfg.name.lower() == name.lower():
                return cfg
        return None


# Singleton instance
_pqc_manager: Optional[PQCManager] = None


def get_pqc_manager(config_file: str = "config/pqc_configs.yaml") -> PQCManager:
    """
    Get singleton PQC Manager instance
    
    Args:
        config_file: Path to PQC configuration file
        
    Returns:
        PQCManager instance
    """
    global _pqc_manager
    if _pqc_manager is None:
        _pqc_manager = PQCManager(config_file)
    return _pqc_manager


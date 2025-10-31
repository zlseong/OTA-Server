"""
ECU Model
Represents an Electronic Control Unit (ECU_001 ~ ECU_100)
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List
from enum import Enum
import re


class ECUStatus(Enum):
    """ECU Status"""
    ACTIVE = "active"
    UPDATING = "updating"
    ERROR = "error"
    OFFLINE = "offline"


class ECUType(Enum):
    """ECU Types"""
    ECM = "ECM"  # Engine Control Module
    TCM = "TCM"  # Transmission Control Module
    BCM = "BCM"  # Body Control Module
    BMS = "BMS"  # Battery Management System
    ADAS_CTL = "ADAS_CTL"  # ADAS Controller
    GENERIC = "GENERIC"  # Generic ECU


@dataclass
class SemanticVersion:
    """
    Semantic Versioning (x.y.z)
    
    - x (major): Breaking changes
    - y (minor): Feature additions
    - z (patch): Bug fixes
    """
    major: int
    minor: int
    patch: int
    
    @classmethod
    def from_string(cls, version_str: str) -> 'SemanticVersion':
        """
        Parse version string (e.g., "1.2.3")
        
        Args:
            version_str: Version string in format "x.y.z"
            
        Returns:
            SemanticVersion instance
            
        Raises:
            ValueError: If format is invalid
        """
        pattern = r'^(\d+)\.(\d+)\.(\d+)$'
        match = re.match(pattern, version_str)
        
        if not match:
            raise ValueError(f"Invalid version format: {version_str}. Expected x.y.z")
        
        major, minor, patch = map(int, match.groups())
        return cls(major=major, minor=minor, patch=patch)
    
    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"
    
    def __eq__(self, other: 'SemanticVersion') -> bool:
        return (self.major, self.minor, self.patch) == (other.major, other.minor, other.patch)
    
    def __lt__(self, other: 'SemanticVersion') -> bool:
        """
        Compare versions (for sorting)
        
        Examples:
            2.0.0 > 1.9.9
            1.5.0 > 1.4.10
            1.0.1 > 1.0.0
        """
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)
    
    def __le__(self, other: 'SemanticVersion') -> bool:
        return self < other or self == other
    
    def __gt__(self, other: 'SemanticVersion') -> bool:
        return not self <= other
    
    def __ge__(self, other: 'SemanticVersion') -> bool:
        return not self < other
    
    def is_compatible_with(self, other: 'SemanticVersion') -> bool:
        """
        Check if versions are compatible (same major version)
        
        Returns:
            True if major versions match
        """
        return self.major == other.major
    
    def get_change_type(self, other: 'SemanticVersion') -> str:
        """
        Determine type of change from current to other version
        
        Returns:
            "major", "minor", "patch", or "none"
        """
        if self.major != other.major:
            return "major"
        elif self.minor != other.minor:
            return "minor"
        elif self.patch != other.patch:
            return "patch"
        else:
            return "none"


@dataclass
class ECU:
    """
    ECU (Electronic Control Unit) Model
    
    Attributes:
        ecu_id: Unique ECU identifier (ECU_001 ~ ECU_100)
        name: Human-readable name
        ecu_type: ECU type (ECM, TCM, etc.)
        hardware_type: Hardware platform (TC375, etc.)
        current_version: Current firmware version
        vehicle_id: Associated vehicle UUID
        zonal_gateway_id: Associated Zonal Gateway UUID
        status: Current ECU status
    """
    ecu_id: str
    name: str
    ecu_type: ECUType
    hardware_type: str
    current_version: SemanticVersion
    
    vehicle_id: Optional[str] = None
    zonal_gateway_id: Optional[str] = None
    
    bootloader_version: Optional[SemanticVersion] = None
    application_version: Optional[SemanticVersion] = None
    
    serial_number: Optional[str] = None
    mac_address: Optional[str] = None
    
    status: ECUStatus = ECUStatus.ACTIVE
    last_seen: Optional[datetime] = None
    
    max_package_size: int = 104857600  # 100 MB
    supports_delta_update: bool = True
    supports_compression: bool = True
    
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def __post_init__(self):
        """Validate ECU ID format"""
        if not self._validate_ecu_id():
            raise ValueError(f"Invalid ECU ID format: {self.ecu_id}. Expected ECU_001 ~ ECU_100")
    
    def _validate_ecu_id(self) -> bool:
        """
        Validate ECU ID format (ECU_001 ~ ECU_100)
        
        Returns:
            True if valid
        """
        pattern = r'^ECU_\d{3}$'
        if not re.match(pattern, self.ecu_id):
            return False
        
        # Extract number and check range
        num = int(self.ecu_id.split('_')[1])
        return 1 <= num <= 100
    
    def needs_update(self, latest_version: SemanticVersion) -> bool:
        """
        Check if ECU needs update
        
        Args:
            latest_version: Latest available version
            
        Returns:
            True if update is needed (current < latest)
        """
        return self.current_version < latest_version
    
    def can_update_to(self, target_version: SemanticVersion) -> tuple[bool, str]:
        """
        Check if ECU can update to target version
        
        Args:
            target_version: Target version
            
        Returns:
            (can_update, reason)
        """
        if self.status != ECUStatus.ACTIVE:
            return False, f"ECU status is {self.status.value}, must be active"
        
        if target_version <= self.current_version:
            return False, f"Target version {target_version} is not newer than current {self.current_version}"
        
        # Check compatibility for major version changes
        if not self.current_version.is_compatible_with(target_version):
            if target_version.major < self.current_version.major:
                return False, "Cannot downgrade major version"
        
        return True, "OK"
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "ecu_id": self.ecu_id,
            "name": self.name,
            "type": self.ecu_type.value,
            "hardware_type": self.hardware_type,
            "current_version": str(self.current_version),
            "bootloader_version": str(self.bootloader_version) if self.bootloader_version else None,
            "application_version": str(self.application_version) if self.application_version else None,
            "vehicle_id": self.vehicle_id,
            "zonal_gateway_id": self.zonal_gateway_id,
            "status": self.status.value,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "capabilities": {
                "max_package_size": self.max_package_size,
                "supports_delta_update": self.supports_delta_update,
                "supports_compression": self.supports_compression
            }
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ECU':
        """Create ECU from dictionary"""
        return cls(
            ecu_id=data['ecu_id'],
            name=data['name'],
            ecu_type=ECUType(data['type']),
            hardware_type=data['hardware_type'],
            current_version=SemanticVersion.from_string(data['current_version']),
            vehicle_id=data.get('vehicle_id'),
            zonal_gateway_id=data.get('zonal_gateway_id'),
            status=ECUStatus(data.get('status', 'active'))
        )


def compare_versions(v1: str, v2: str) -> int:
    """
    Compare two version strings
    
    Args:
        v1: First version string
        v2: Second version string
        
    Returns:
        -1 if v1 < v2
         0 if v1 == v2
         1 if v1 > v2
    """
    ver1 = SemanticVersion.from_string(v1)
    ver2 = SemanticVersion.from_string(v2)
    
    if ver1 < ver2:
        return -1
    elif ver1 > ver2:
        return 1
    else:
        return 0


def get_latest_version(versions: List[str]) -> str:
    """
    Get latest version from list of version strings
    
    Args:
        versions: List of version strings
        
    Returns:
        Latest version string
    """
    if not versions:
        raise ValueError("Empty version list")
    
    semantic_versions = [SemanticVersion.from_string(v) for v in versions]
    latest = max(semantic_versions)
    return str(latest)


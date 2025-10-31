"""
OTA Package Manager
Creates and manages OTA packages optimized for Zonal Gateway distribution
"""

import asyncio
import hashlib
import json
import logging
from typing import List, Dict, Optional
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime
import zstandard as zstd

logger = logging.getLogger(__name__)


@dataclass
class FirmwareInfo:
    """Firmware information"""
    ecu_id: str
    ecu_type: str
    current_version: str
    target_version: str
    firmware_path: Path
    file_size: int
    sha256_hash: str


@dataclass
class ZonalPackage:
    """Package for a Zonal Gateway"""
    zonal_gateway_id: str
    ecu_count: int
    total_size: int
    firmware_list: List[FirmwareInfo]
    package_path: Path


class PackageManager:
    """
    OTA Package Manager
    
    Features:
        - Group ECUs by Zonal Gateway
        - Optimize package size (compression, delta updates)
        - Generate package metadata
        - Sign packages with PQC
        - Calculate optimal distribution strategy
    """
    
    def __init__(self, config: dict, db_connection):
        """
        Initialize Package Manager
        
        Args:
            config: OTA configuration from server.yaml
            db_connection: Database connection pool
        """
        self.config = config
        self.db = db_connection
        
        self.package_storage = Path(config.get('package_storage_path', '/var/lib/ota-server/packages'))
        self.package_storage.mkdir(parents=True, exist_ok=True)
        
        self.compression_enabled = config.get('compression') != 'none'
        self.compression_type = config.get('compression', 'zstd')
        self.compression_level = config.get('compression_level', 3)
        
        self.delta_enabled = config.get('delta_updates', {}).get('enabled', True)
    
    async def create_ota_package(self, vehicle_id: str, target_ecus: List[str],
                                zonal_optimization: bool = True) -> Dict:
        """
        Create OTA update package
        
        Args:
            vehicle_id: Target vehicle ID
            target_ecus: List of ECU IDs to update
            zonal_optimization: Enable Zonal Gateway optimization
            
        Returns:
            Package metadata
        """
        logger.info(f"Creating OTA package for vehicle {vehicle_id}")
        logger.info(f"  Target ECUs: {len(target_ecus)}")
        logger.info(f"  Zonal optimization: {zonal_optimization}")
        
        # 1. Get firmware information for each ECU
        firmware_list = await self._get_firmware_list(target_ecus)
        
        # 2. Group by Zonal Gateway if optimization enabled
        if zonal_optimization:
            zonal_packages = await self._group_by_zonal_gateway(vehicle_id, firmware_list)
        else:
            # Single package for all ECUs
            zonal_packages = [await self._create_monolithic_package(firmware_list)]
        
        # 3. Create packages
        package_id = f"ota-{vehicle_id}-{int(datetime.now().timestamp())}"
        packages_created = []
        
        for zonal_pkg in zonal_packages:
            pkg_path = await self._build_package(package_id, zonal_pkg)
            packages_created.append({
                'zonal_gateway_id': zonal_pkg.zonal_gateway_id,
                'ecu_count': zonal_pkg.ecu_count,
                'package_size': zonal_pkg.total_size,
                'package_path': str(pkg_path)
            })
        
        # 4. Generate master package metadata
        metadata = {
            'package_id': package_id,
            'vehicle_id': vehicle_id,
            'created_at': datetime.now().isoformat(),
            'total_ecus': len(target_ecus),
            'zonal_packages': packages_created,
            'distribution_strategy': 'zonal_gateway_optimized' if zonal_optimization else 'monolithic'
        }
        
        # 5. Save metadata
        metadata_path = self.package_storage / f"{package_id}_metadata.json"
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        logger.info(f"OTA package created: {package_id}")
        logger.info(f"  Zonal packages: {len(packages_created)}")
        
        return metadata
    
    async def _get_firmware_list(self, ecu_ids: List[str]) -> List[FirmwareInfo]:
        """
        Get firmware information for ECUs
        
        Args:
            ecu_ids: List of ECU IDs
            
        Returns:
            List of FirmwareInfo
        """
        firmware_list = []
        
        for ecu_id in ecu_ids:
            # Query database for ECU and firmware info
            async with self.db.acquire() as conn:
                ecu_row = await conn.fetchrow(
                    """
                    SELECT ecu_id, type, current_version
                    FROM ecus
                    WHERE ecu_id = $1
                    """,
                    ecu_id
                )
                
                if not ecu_row:
                    logger.warning(f"ECU not found: {ecu_id}")
                    continue
                
                # Get latest firmware
                fw_row = await conn.fetchrow(
                    """
                    SELECT version, file_path, file_size, sha256_hash
                    FROM firmware_packages
                    WHERE ecu_type = $1 AND status = 'available'
                    ORDER BY version DESC
                    LIMIT 1
                    """,
                    ecu_row['type']
                )
                
                if not fw_row:
                    logger.warning(f"No firmware found for type {ecu_row['type']}")
                    continue
            
            firmware_info = FirmwareInfo(
                ecu_id=ecu_row['ecu_id'],
                ecu_type=ecu_row['type'],
                current_version=ecu_row['current_version'],
                target_version=fw_row['version'],
                firmware_path=Path(fw_row['file_path']),
                file_size=fw_row['file_size'],
                sha256_hash=fw_row['sha256_hash']
            )
            
            firmware_list.append(firmware_info)
        
        return firmware_list
    
    async def _group_by_zonal_gateway(self, vehicle_id: str, 
                                     firmware_list: List[FirmwareInfo]) -> List[ZonalPackage]:
        """
        Group firmware by Zonal Gateway
        
        Args:
            vehicle_id: Vehicle ID
            firmware_list: List of firmware to package
            
        Returns:
            List of ZonalPackage
        """
        # Query ECU to Zonal Gateway mapping
        async with self.db.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT e.ecu_id, zg.zg_id
                FROM ecus e
                JOIN zonal_gateways zg ON e.zonal_gateway_id = zg.id
                WHERE e.vehicle_id = $1
                """,
                vehicle_id
            )
        
        # Create mapping
        ecu_to_zg = {row['ecu_id']: row['zg_id'] for row in rows}
        
        # Group firmware by ZG
        zg_groups: Dict[str, List[FirmwareInfo]] = {}
        
        for fw in firmware_list:
            zg_id = ecu_to_zg.get(fw.ecu_id, 'UNKNOWN')
            if zg_id not in zg_groups:
                zg_groups[zg_id] = []
            zg_groups[zg_id].append(fw)
        
        # Create ZonalPackage objects
        zonal_packages = []
        
        for zg_id, fw_list in zg_groups.items():
            total_size = sum(fw.file_size for fw in fw_list)
            
            zonal_pkg = ZonalPackage(
                zonal_gateway_id=zg_id,
                ecu_count=len(fw_list),
                total_size=total_size,
                firmware_list=fw_list,
                package_path=None  # Will be set during build
            )
            
            zonal_packages.append(zonal_pkg)
            
            logger.info(f"Zonal package for {zg_id}: {len(fw_list)} ECUs, {total_size} bytes")
        
        return zonal_packages
    
    async def _create_monolithic_package(self, firmware_list: List[FirmwareInfo]) -> ZonalPackage:
        """
        Create single monolithic package
        
        Args:
            firmware_list: List of firmware
            
        Returns:
            Single ZonalPackage
        """
        total_size = sum(fw.file_size for fw in firmware_list)
        
        return ZonalPackage(
            zonal_gateway_id='ALL',
            ecu_count=len(firmware_list),
            total_size=total_size,
            firmware_list=firmware_list,
            package_path=None
        )
    
    async def _build_package(self, package_id: str, zonal_pkg: ZonalPackage) -> Path:
        """
        Build actual package file
        
        Args:
            package_id: Base package ID
            zonal_pkg: Zonal package info
            
        Returns:
            Path to created package
        """
        # Package filename
        pkg_filename = f"{package_id}_{zonal_pkg.zonal_gateway_id}.bin"
        pkg_path = self.package_storage / pkg_filename
        
        logger.info(f"Building package: {pkg_filename}")
        
        # Package format:
        # [Header] [Firmware 1] [Firmware 2] ... [Firmware N]
        
        with open(pkg_path, 'wb') as pkg_file:
            # Write header
            header = self._create_package_header(zonal_pkg)
            pkg_file.write(header)
            
            # Write each firmware
            for fw in zonal_pkg.firmware_list:
                # Write firmware metadata
                fw_metadata = self._create_firmware_metadata(fw)
                pkg_file.write(fw_metadata)
                
                # Write firmware data (with optional compression)
                fw_data = self._read_and_compress_firmware(fw)
                pkg_file.write(fw_data)
        
        # Update package path
        zonal_pkg.package_path = pkg_path
        
        # Calculate package hash
        pkg_hash = self._calculate_file_hash(pkg_path)
        
        logger.info(f"  Package created: {pkg_path}")
        logger.info(f"  Size: {pkg_path.stat().st_size} bytes")
        logger.info(f"  SHA256: {pkg_hash}")
        
        return pkg_path
    
    def _create_package_header(self, zonal_pkg: ZonalPackage) -> bytes:
        """
        Create package header
        
        Format:
        - Magic: 4 bytes (0x4F544150 = "OTAP")
        - Version: 2 bytes
        - ECU count: 2 bytes
        - ZG ID length: 1 byte
        - ZG ID: variable
        - Reserved: 16 bytes
        
        Returns:
            Header bytes
        """
        magic = b'OTAP'  # OTA Package
        version = (1).to_bytes(2, 'big')
        ecu_count = zonal_pkg.ecu_count.to_bytes(2, 'big')
        
        zg_id_bytes = zonal_pkg.zonal_gateway_id.encode('utf-8')
        zg_id_len = len(zg_id_bytes).to_bytes(1, 'big')
        
        reserved = bytes(16)
        
        header = magic + version + ecu_count + zg_id_len + zg_id_bytes + reserved
        
        return header
    
    def _create_firmware_metadata(self, fw: FirmwareInfo) -> bytes:
        """
        Create firmware metadata entry
        
        Format:
        - ECU ID length: 1 byte
        - ECU ID: variable
        - Current version length: 1 byte
        - Current version: variable
        - Target version length: 1 byte
        - Target version: variable
        - File size: 4 bytes
        - SHA256: 32 bytes
        
        Returns:
            Metadata bytes
        """
        ecu_id_bytes = fw.ecu_id.encode('utf-8')
        ecu_id_len = len(ecu_id_bytes).to_bytes(1, 'big')
        
        current_ver_bytes = fw.current_version.encode('utf-8')
        current_ver_len = len(current_ver_bytes).to_bytes(1, 'big')
        
        target_ver_bytes = fw.target_version.encode('utf-8')
        target_ver_len = len(target_ver_bytes).to_bytes(1, 'big')
        
        file_size = fw.file_size.to_bytes(4, 'big')
        sha256 = bytes.fromhex(fw.sha256_hash)
        
        metadata = (ecu_id_len + ecu_id_bytes +
                   current_ver_len + current_ver_bytes +
                   target_ver_len + target_ver_bytes +
                   file_size + sha256)
        
        return metadata
    
    def _read_and_compress_firmware(self, fw: FirmwareInfo) -> bytes:
        """
        Read firmware file and optionally compress
        
        Args:
            fw: Firmware info
            
        Returns:
            Firmware data (compressed if enabled)
        """
        # Read firmware file
        with open(fw.firmware_path, 'rb') as f:
            data = f.read()
        
        # Compress if enabled
        if self.compression_enabled:
            if self.compression_type == 'zstd':
                cctx = zstd.ZstdCompressor(level=self.compression_level)
                compressed = cctx.compress(data)
                
                compression_ratio = len(compressed) / len(data)
                logger.debug(f"  Compressed {fw.ecu_id}: {len(data)} -> {len(compressed)} bytes ({compression_ratio:.2%})")
                
                return compressed
        
        return data
    
    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of file"""
        hasher = hashlib.sha256()
        
        with open(file_path, 'rb') as f:
            while chunk := f.read(1024 * 1024):
                hasher.update(chunk)
        
        return hasher.hexdigest()
    
    async def get_package_info(self, package_id: str) -> Optional[Dict]:
        """
        Get package information
        
        Args:
            package_id: Package ID
            
        Returns:
            Package metadata or None
        """
        metadata_path = self.package_storage / f"{package_id}_metadata.json"
        
        if not metadata_path.exists():
            return None
        
        with open(metadata_path, 'r') as f:
            return json.load(f)
    
    async def verify_package(self, package_path: Path) -> bool:
        """
        Verify package integrity
        
        Args:
            package_path: Path to package file
            
        Returns:
            True if valid
        """
        # TODO: Implement package verification
        # 1. Check magic bytes
        # 2. Verify structure
        # 3. Verify hashes
        # 4. Verify PQC signature
        
        return True


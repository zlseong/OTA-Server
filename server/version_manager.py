"""
ECU Version Manager
Manages versions for ECU_001 ~ ECU_100
"""

import asyncio
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import logging

from models.ecu import ECU, SemanticVersion, compare_versions

logger = logging.getLogger(__name__)


@dataclass
class VersionCheckResult:
    """Result of version check"""
    ecu_id: str
    current_version: str
    latest_version: str
    needs_update: bool
    update_type: str  # "major", "minor", "patch"
    priority: int  # 0=low, 1=medium, 2=high, 3=critical


class VersionManager:
    """
    Manages ECU versions and update requirements
    
    Features:
        - Track versions for 100 ECUs
        - Compare semantic versions
        - Identify outdated ECUs
        - Prioritize updates
    """
    
    def __init__(self, db_connection):
        """
        Initialize Version Manager
        
        Args:
            db_connection: Database connection pool
        """
        self.db = db_connection
        self.cache = {}  # ECU ID -> latest version cache
        self.cache_timestamp = None
    
    async def check_ecu_version(self, ecu_id: str) -> VersionCheckResult:
        """
        Check if ECU needs update
        
        Args:
            ecu_id: ECU identifier (ECU_001 ~ ECU_100)
            
        Returns:
            VersionCheckResult with update info
        """
        # Get current version from database
        async with self.db.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT current_version, type FROM ecus WHERE ecu_id = $1",
                ecu_id
            )
        
        if not row:
            raise ValueError(f"ECU {ecu_id} not found")
        
        current_version_str = row['current_version']
        ecu_type = row['type']
        
        # Get latest available version
        latest_version_str = await self._get_latest_version(ecu_type)
        
        # Parse versions
        current = SemanticVersion.from_string(current_version_str)
        latest = SemanticVersion.from_string(latest_version_str)
        
        # Determine update type and priority
        needs_update = current < latest
        update_type = current.get_change_type(latest) if needs_update else "none"
        priority = self._calculate_priority(update_type, current, latest)
        
        return VersionCheckResult(
            ecu_id=ecu_id,
            current_version=current_version_str,
            latest_version=latest_version_str,
            needs_update=needs_update,
            update_type=update_type,
            priority=priority
        )
    
    async def check_all_ecus(self, vehicle_id: str) -> List[VersionCheckResult]:
        """
        Check versions for all ECUs in a vehicle
        
        Args:
            vehicle_id: Vehicle UUID
            
        Returns:
            List of VersionCheckResults
        """
        # Get all ECUs for this vehicle
        async with self.db.acquire() as conn:
            rows = await conn.fetch(
                "SELECT ecu_id FROM ecus WHERE vehicle_id = $1",
                vehicle_id
            )
        
        ecu_ids = [row['ecu_id'] for row in rows]
        
        # Check versions concurrently
        tasks = [self.check_ecu_version(ecu_id) for ecu_id in ecu_ids]
        results = await asyncio.gather(*tasks)
        
        return results
    
    async def get_outdated_ecus(self, vehicle_id: str) -> List[VersionCheckResult]:
        """
        Get ECUs that need updates
        
        Args:
            vehicle_id: Vehicle UUID
            
        Returns:
            List of outdated ECUs sorted by priority
        """
        results = await self.check_all_ecus(vehicle_id)
        
        # Filter outdated ECUs
        outdated = [r for r in results if r.needs_update]
        
        # Sort by priority (high to low)
        outdated.sort(key=lambda x: x.priority, reverse=True)
        
        return outdated
    
    async def get_update_statistics(self, vehicle_id: str) -> Dict:
        """
        Get update statistics for a vehicle
        
        Args:
            vehicle_id: Vehicle UUID
            
        Returns:
            Statistics dictionary
        """
        results = await self.check_all_ecus(vehicle_id)
        
        total = len(results)
        outdated = sum(1 for r in results if r.needs_update)
        up_to_date = total - outdated
        
        # Count by update type
        major_updates = sum(1 for r in results if r.update_type == "major")
        minor_updates = sum(1 for r in results if r.update_type == "minor")
        patch_updates = sum(1 for r in results if r.update_type == "patch")
        
        # Count by priority
        critical = sum(1 for r in results if r.priority == 3)
        high = sum(1 for r in results if r.priority == 2)
        medium = sum(1 for r in results if r.priority == 1)
        low = sum(1 for r in results if r.priority == 0)
        
        return {
            "total_ecus": total,
            "up_to_date": up_to_date,
            "needs_update": outdated,
            "update_types": {
                "major": major_updates,
                "minor": minor_updates,
                "patch": patch_updates
            },
            "priorities": {
                "critical": critical,
                "high": high,
                "medium": medium,
                "low": low
            }
        }
    
    async def bulk_check_versions(self, ecu_ids: List[str]) -> Dict[str, VersionCheckResult]:
        """
        Check versions for multiple ECUs
        
        Args:
            ecu_ids: List of ECU identifiers
            
        Returns:
            Dictionary mapping ECU ID to VersionCheckResult
        """
        tasks = [self.check_ecu_version(ecu_id) for ecu_id in ecu_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        return {
            ecu_id: result
            for ecu_id, result in zip(ecu_ids, results)
            if not isinstance(result, Exception)
        }
    
    async def update_ecu_version(self, ecu_id: str, new_version: str) -> bool:
        """
        Update ECU version in database
        
        Args:
            ecu_id: ECU identifier
            new_version: New version string (x.y.z)
            
        Returns:
            True if successful
        """
        # Validate version format
        try:
            SemanticVersion.from_string(new_version)
        except ValueError as e:
            logger.error(f"Invalid version format: {e}")
            return False
        
        # Update database
        async with self.db.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE ecus 
                SET current_version = $1, updated_at = NOW()
                WHERE ecu_id = $2
                """,
                new_version, ecu_id
            )
        
        logger.info(f"Updated {ecu_id} to version {new_version}")
        return True
    
    async def _get_latest_version(self, ecu_type: str) -> str:
        """
        Get latest available version for ECU type
        
        Args:
            ecu_type: ECU type (ECM, TCM, etc.)
            
        Returns:
            Latest version string
        """
        # Check cache first
        cache_key = f"latest_{ecu_type}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        # Query database
        async with self.db.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT version FROM firmware_packages
                WHERE ecu_type = $1 AND status = 'available'
                ORDER BY version DESC
                LIMIT 1
                """,
                ecu_type
            )
        
        if not row:
            logger.warning(f"No firmware package found for type {ecu_type}")
            return "0.0.0"
        
        latest_version = row['version']
        
        # Update cache
        self.cache[cache_key] = latest_version
        
        return latest_version
    
    def _calculate_priority(self, update_type: str, current: SemanticVersion, 
                           latest: SemanticVersion) -> int:
        """
        Calculate update priority
        
        Args:
            update_type: "major", "minor", or "patch"
            current: Current version
            latest: Latest version
            
        Returns:
            Priority level (0-3)
        """
        # Base priority by update type
        priority_map = {
            "major": 2,   # High
            "minor": 1,   # Medium
            "patch": 0    # Low
        }
        
        base_priority = priority_map.get(update_type, 0)
        
        # Increase priority for security patches
        # (Assume patch version >= 10 indicates security fix)
        if update_type == "patch" and latest.patch >= 10:
            base_priority = 2
        
        # Increase priority if version is very old
        version_gap = (latest.major - current.major) * 100 + \
                     (latest.minor - current.minor) * 10 + \
                     (latest.patch - current.patch)
        
        if version_gap > 50:
            base_priority = min(base_priority + 1, 3)
        
        return base_priority
    
    async def clear_cache(self):
        """Clear version cache"""
        self.cache.clear()
        self.cache_timestamp = None
        logger.info("Version cache cleared")


# Utility functions

async def compare_vehicle_versions(db, vehicle_id: str) -> Dict:
    """
    Compare all ECU versions in a vehicle
    
    Args:
        db: Database connection
        vehicle_id: Vehicle UUID
        
    Returns:
        Comparison results
    """
    manager = VersionManager(db)
    results = await manager.check_all_ecus(vehicle_id)
    
    return {
        "vehicle_id": vehicle_id,
        "check_time": datetime.now().isoformat(),
        "ecus": [
            {
                "ecu_id": r.ecu_id,
                "current": r.current_version,
                "latest": r.latest_version,
                "status": "outdated" if r.needs_update else "up-to-date",
                "update_type": r.update_type if r.needs_update else None,
                "priority": r.priority if r.needs_update else None
            }
            for r in results
        ]
    }


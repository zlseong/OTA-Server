#!/usr/bin/env python3
"""
OTA Package Builder for Zonal E/E Architecture
Builds hierarchical OTA packages with 64-byte headers
"""

import os
import sys
import struct
import zlib
import hashlib
import json
from datetime import datetime
from typing import Dict, List, Tuple

# ===== Software Package Header =====
# Total: 64 bytes
# See: OTA_SERVER_ARCHITECTURE.md

MAGIC_NUMBER = 0x53575047  # "SWPG"

ECU_IDS = {
    "VMG":     0x0E00,
    "ZGW":     0x0091,
    "ECU_011": 0x0011,
    "ECU_012": 0x0012,
    "ECU_013": 0x0013,
    "ECU_021": 0x0021,
    "ECU_022": 0x0022,
}

SOFTWARE_TYPES = {
    "APP":  0x01,
    "BOOT": 0x02,
    "CAL":  0x03,
    "CFG":  0x04,
}

class SoftwarePackageHeader:
    """64-byte Software Package Header"""
    
    def __init__(self):
        # Identification (16 bytes)
        self.magic = MAGIC_NUMBER
        self.target_ecu_id = 0
        self.software_type = SOFTWARE_TYPES["APP"]
        self.compression = 0  # 0=none, 1=gzip
        self.payload_size = 0
        self.uncompressed_size = 0
        
        # Version Information (12 bytes)
        self.version_major = 0
        self.version_minor = 0
        self.version_patch = 0
        self.version_build = 0
        self.version_timestamp = 0
        self.version_serial = 0
        
        # Security & Integrity (16 bytes)
        self.crc32 = 0
        self.signature = [0, 0, 0]  # Reserved
        
        # Routing Information (8 bytes)
        self.source_ecu_id = 0x0000  # Server
        self.hop_count = 0
        self.sequence_number = 0
        
        # Reserved (12 bytes)
        self.reserved = bytes(12)
    
    def pack(self):
        """Pack header to 64-byte binary"""
        data = struct.pack(
            '<I H B B I I '     # Identification (16 bytes)
            'B B B B I I '      # Version (12 bytes)
            'I I I I '          # Security (16 bytes)
            'H H I '            # Routing (8 bytes)
            '12s',              # Reserved (12 bytes)
            
            self.magic,
            self.target_ecu_id,
            self.software_type,
            self.compression,
            self.payload_size,
            self.uncompressed_size,
            
            self.version_major,
            self.version_minor,
            self.version_patch,
            self.version_build,
            self.version_timestamp,
            self.version_serial,
            
            self.crc32,
            self.signature[0],
            self.signature[1],
            self.signature[2],
            
            self.source_ecu_id,
            self.hop_count,
            self.sequence_number,
            
            self.reserved
        )
        
        assert len(data) == 64, f"Header size must be 64 bytes, got {len(data)}"
        return data
    
    @staticmethod
    def unpack(data):
        """Unpack 64-byte binary to header"""
        assert len(data) == 64, "Header must be 64 bytes"
        
        values = struct.unpack('<I H B B I I B B B B I I I I I I H H I 12s', data)
        
        header = SoftwarePackageHeader()
        header.magic = values[0]
        header.target_ecu_id = values[1]
        header.software_type = values[2]
        header.compression = values[3]
        header.payload_size = values[4]
        header.uncompressed_size = values[5]
        
        header.version_major = values[6]
        header.version_minor = values[7]
        header.version_patch = values[8]
        header.version_build = values[9]
        header.version_timestamp = values[10]
        header.version_serial = values[11]
        
        header.crc32 = values[12]
        header.signature = [values[13], values[14], values[15]]
        
        header.source_ecu_id = values[16]
        header.hop_count = values[17]
        header.sequence_number = values[18]
        
        header.reserved = values[19]
        
        return header


class PackageBuilder:
    """OTA Package Builder"""
    
    def __init__(self, campaign_id, output_dir, signing_key_path=None):
        self.campaign_id = campaign_id
        self.output_dir = output_dir
        self.signing_key = None
        
        if signing_key_path:
            try:
                from Crypto.PublicKey import RSA
                with open(signing_key_path, 'rb') as f:
                    self.signing_key = RSA.import_key(f.read())
            except ImportError:
                print("[WARNING] pycryptodome not installed. Signatures will be skipped.")
            except Exception as e:
                print(f"[WARNING] Failed to load signing key: {e}")
        
        os.makedirs(output_dir, exist_ok=True)
    
    def build_package(self, ecu_name, binary_path, version, compress=False):
        """
        Build a single ECU package with header
        
        Args:
            ecu_name: "VMG", "ZGW", "ECU_011", etc.
            binary_path: Path to raw binary file
            version: (major, minor, patch, build) tuple
            compress: Enable gzip compression
        
        Returns:
            Package metadata dictionary
        """
        print(f"\n=== Building package for {ecu_name} ===")
        
        # Read raw binary
        with open(binary_path, 'rb') as f:
            payload = f.read()
        
        print(f"Raw binary size: {len(payload)} bytes ({len(payload)/1024:.2f} KB)")
        
        # Compress if requested
        uncompressed_size = len(payload)
        if compress:
            payload = zlib.compress(payload, level=9)
            print(f"Compressed size: {len(payload)} bytes ({len(payload)/1024:.2f} KB)")
            print(f"Compression ratio: {100 * (1 - len(payload)/uncompressed_size):.1f}%")
        
        # Calculate CRC32
        crc32 = zlib.crc32(payload) & 0xFFFFFFFF
        print(f"CRC32: 0x{crc32:08X}")
        
        # Build header
        header = SoftwarePackageHeader()
        header.target_ecu_id = ECU_IDS[ecu_name]
        header.payload_size = len(payload)
        header.uncompressed_size = uncompressed_size
        header.compression = 1 if compress else 0
        
        header.version_major = version[0]
        header.version_minor = version[1]
        header.version_patch = version[2]
        header.version_build = version[3]
        header.version_timestamp = int(datetime.now().timestamp())
        header.version_serial = int(datetime.now().strftime("%Y%m%d%H%M"))
        
        header.crc32 = crc32
        
        # Pack header
        header_bytes = header.pack()
        
        # Combine header + payload
        package = header_bytes + payload
        
        # Write package
        package_filename = f"{ecu_name.lower()}_sw_package.bin"
        package_path = os.path.join(self.output_dir, package_filename)
        
        with open(package_path, 'wb') as f:
            f.write(package)
        
        print(f"Package created: {package_path}")
        print(f"Total size: {len(package)} bytes ({len(package)/1024:.2f} KB)")
        
        # Calculate SHA256 for metadata
        sha256 = hashlib.sha256(package).hexdigest()
        
        return {
            "package_id": f"pkg-{ecu_name.lower()}-{version[0]}.{version[1]}.{version[2]}",
            "target_ecu": ecu_name,
            "ecu_id": f"0x{header.target_ecu_id:04X}",
            "version": f"{version[0]}.{version[1]}.{version[2]}-{version[3]}",
            "file_path": package_path,
            "file_name": package_filename,
            "size_bytes": len(package),
            "payload_size_bytes": len(payload),
            "header_size_bytes": 64,
            "compression": "gzip" if compress else "none",
            "crc32": f"0x{crc32:08X}",
            "sha256": sha256,
        }
    
    def build_campaign(self, packages_config):
        """
        Build complete OTA campaign
        
        Args:
            packages_config: Dictionary with ECU configs
            
        Example:
            {
                "VMG": {"binary": "vmg_2.2.0.bin", "version": (2, 2, 0, 100)},
                "ZGW": {"binary": "zgw_1.2.0.bin", "version": (1, 2, 0, 50)},
                "ECU_011": {"binary": "ecu011_1.1.0.bin", "version": (1, 1, 0, 10)},
            }
        """
        campaign_dir = os.path.join(self.output_dir, f"Campaign_{self.campaign_id}")
        os.makedirs(campaign_dir, exist_ok=True)
        
        metadata = {
            "campaign_id": self.campaign_id,
            "created_at": datetime.now().isoformat(),
            "packages": []
        }
        
        # Build VMG package
        if "VMG" in packages_config:
            vmg_dir = os.path.join(campaign_dir, "vmg_package")
            os.makedirs(vmg_dir, exist_ok=True)
            
            builder = PackageBuilder(self.campaign_id, vmg_dir, None)
            vmg_pkg = builder.build_package(
                "VMG",
                packages_config["VMG"]["binary"],
                packages_config["VMG"]["version"],
                compress=packages_config["VMG"].get("compress", False)
            )
            metadata["packages"].append(vmg_pkg)
        
        # Build Zone packages
        zone_ecus = [k for k in packages_config.keys() if k != "VMG"]
        if zone_ecus:
            zone_dir = os.path.join(campaign_dir, "zone1_package")
            os.makedirs(zone_dir, exist_ok=True)
            
            builder = PackageBuilder(self.campaign_id, zone_dir, None)
            
            for ecu_name in zone_ecus:
                pkg = builder.build_package(
                    ecu_name,
                    packages_config[ecu_name]["binary"],
                    packages_config[ecu_name]["version"],
                    compress=packages_config[ecu_name].get("compress", False)
                )
                metadata["packages"].append(pkg)
        
        # Write campaign metadata
        metadata_path = os.path.join(campaign_dir, "campaign_metadata.json")
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        print(f"\n=== Campaign {self.campaign_id} created ===")
        print(f"Output directory: {campaign_dir}")
        print(f"Total packages: {len(metadata['packages'])}")
        print(f"Metadata: {metadata_path}")
        
        return metadata


# ===== Header Verification Tool =====

def verify_package(package_path):
    """Verify OTA package header"""
    with open(package_path, 'rb') as f:
        header_bytes = f.read(64)
    
    if len(header_bytes) != 64:
        print(f"ERROR: Header must be 64 bytes, got {len(header_bytes)}")
        return False
    
    # Parse header
    header = SoftwarePackageHeader.unpack(header_bytes)
    
    # Verify magic
    if header.magic != 0x53575047:
        print(f"ERROR: Invalid magic 0x{header.magic:08X} (expected 0x53575047)")
        return False
    
    print("=== Package Header ===")
    print(f"Magic:       0x{header.magic:08X} ✓")
    print(f"ECU ID:      0x{header.target_ecu_id:04X}")
    print(f"SW Type:     {header.software_type} ({'APP' if header.software_type == 1 else 'BOOT' if header.software_type == 2 else 'UNKNOWN'})")
    print(f"Compression: {header.compression} ({'gzip' if header.compression == 1 else 'none'})")
    print(f"Payload:     {header.payload_size} bytes ({header.payload_size/1024:.2f} KB)")
    print(f"Uncompressed: {header.uncompressed_size} bytes")
    print(f"Version:     {header.version_major}.{header.version_minor}.{header.version_patch}-{header.version_build}")
    print(f"Timestamp:   {header.version_timestamp}")
    print(f"CRC32:       0x{header.crc32:08X}")
    
    return True


# ===== CLI =====

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="OTA Package Builder")
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Build command
    build_parser = subparsers.add_parser('build', help='Build OTA campaign')
    build_parser.add_argument("--campaign-id", required=True, help="Campaign ID")
    build_parser.add_argument("--vmg-binary", help="VMG binary file")
    build_parser.add_argument("--vmg-version", default="2.2.0.100", help="VMG version (major.minor.patch.build)")
    build_parser.add_argument("--zgw-binary", help="ZGW binary file")
    build_parser.add_argument("--zgw-version", default="1.2.0.50", help="ZGW version")
    build_parser.add_argument("--ecu-011-binary", help="ECU_011 binary file")
    build_parser.add_argument("--ecu-011-version", default="1.1.0.10", help="ECU_011 version")
    build_parser.add_argument("--ecu-012-binary", help="ECU_012 binary file")
    build_parser.add_argument("--ecu-012-version", default="1.1.0.10", help="ECU_012 version")
    build_parser.add_argument("--output-dir", default="./campaigns", help="Output directory")
    build_parser.add_argument("--signing-key", help="RSA private key for signing (optional)")
    build_parser.add_argument("--compress", action="store_true", help="Enable gzip compression")
    
    # Verify command
    verify_parser = subparsers.add_parser('verify', help='Verify OTA package')
    verify_parser.add_argument("package", help="Package file to verify")
    
    args = parser.parse_args()
    
    if args.command == 'build':
        # Parse versions
        def parse_version(ver_str):
            parts = ver_str.split('.')
            return (int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3]))
        
        # Build config
        config = {}
        
        if args.vmg_binary:
            config["VMG"] = {
                "binary": args.vmg_binary,
                "version": parse_version(args.vmg_version),
                "compress": args.compress
            }
        
        if args.zgw_binary:
            config["ZGW"] = {
                "binary": args.zgw_binary,
                "version": parse_version(args.zgw_version),
                "compress": args.compress
            }
        
        if args.ecu_011_binary:
            config["ECU_011"] = {
                "binary": args.ecu_011_binary,
                "version": parse_version(args.ecu_011_version),
                "compress": args.compress
            }
        
        if args.ecu_012_binary:
            config["ECU_012"] = {
                "binary": args.ecu_012_binary,
                "version": parse_version(args.ecu_012_version),
                "compress": args.compress
            }
        
        if not config:
            print("Error: At least one binary file must be specified")
            sys.exit(1)
        
        # Build campaign
        builder = PackageBuilder(args.campaign_id, args.output_dir, args.signing_key)
        metadata = builder.build_campaign(config)
        
        print("\n=== SUCCESS ===")
        print(f"Campaign packages ready for deployment")
    
    elif args.command == 'verify':
        verify_package(args.package)
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()


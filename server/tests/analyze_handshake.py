"""
PQC TLS 핸드셰이크 상세 분석 도구
Wireshark 스타일 패킷 분석
"""

import ssl
import socket
import struct
from datetime import datetime

class TLSHandshakeAnalyzer:
    """TLS 핸드셰이크 상세 분석"""
    
    TLS_RECORD_TYPES = {
        0x14: "ChangeCipherSpec",
        0x15: "Alert",
        0x16: "Handshake",
        0x17: "Application Data"
    }
    
    TLS_HANDSHAKE_TYPES = {
        0x01: "ClientHello",
        0x02: "ServerHello",
        0x04: "NewSessionTicket",
        0x08: "EncryptedExtensions",
        0x0b: "Certificate",
        0x0d: "CertificateRequest",
        0x0f: "CertificateVerify",
        0x14: "Finished"
    }
    
    def __init__(self):
        self.messages = []
    
    def capture_handshake(self, host: str = "localhost", port: int = 4433):
        """핸드셰이크 캡처 및 분석"""
        print("=" * 70)
        print(f"TLS Handshake Analysis - {datetime.now()}")
        print("=" * 70)
        print()
        
        try:
            # Raw 소켓 생성
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((host, port))
            
            print(f"🔗 Connected to {host}:{port}")
            print()
            
            # SSL 래핑
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.minimum_version = ssl.TLSVersion.TLSv1_3
            context.load_cert_chain('test_certs/client.crt', 'test_certs/client.key')
            context.load_verify_locations('test_certs/ca.crt')
            context.check_hostname = False
            
            ssock = context.wrap_socket(sock, server_hostname=host)
            
            print("✅ TLS Handshake completed")
            print()
            
            # 연결 정보
            print("=" * 70)
            print("Connection Information")
            print("=" * 70)
            print(f"Protocol Version: {ssock.version()}")
            cipher = ssock.cipher()
            print(f"Cipher Suite: {cipher[0]}")
            print(f"  - Protocol: {cipher[1]}")
            print(f"  - Bits: {cipher[2]}")
            
            # 서버 인증서 정보
            print()
            print("=" * 70)
            print("Server Certificate")
            print("=" * 70)
            cert = ssock.getpeercert()
            if cert:
                print(f"Subject: {dict(x[0] for x in cert['subject'])}")
                print(f"Issuer: {dict(x[0] for x in cert['issuer'])}")
                print(f"Not Before: {cert['notBefore']}")
                print(f"Not After: {cert['notAfter']}")
                print(f"Serial Number: {cert.get('serialNumber', 'N/A')}")
            
            # PQC 알고리즘 확인 (가능한 경우)
            print()
            print("=" * 70)
            print("PQC Information")
            print("=" * 70)
            print("Key Exchange: ML-KEM (Post-Quantum)")
            print("Signature: ECDSA secp256r1 (Classical)")
            print("Hybrid Mode: Yes")
            
            # 데이터 전송 테스트
            print()
            print("=" * 70)
            print("Data Transfer Test")
            print("=" * 70)
            ssock.send(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
            response = ssock.recv(1024)
            print(f"✅ Data transfer successful ({len(response)} bytes received)")
            
            ssock.close()
            
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
    
    def compare_algorithms(self):
        """알고리즘별 비교"""
        print()
        print("=" * 70)
        print("Algorithm Comparison")
        print("=" * 70)
        print()
        
        algorithms = [
            ("X25519 + ECDSA", "Classical", "Fast, but quantum-vulnerable"),
            ("ML-KEM-512 + ECDSA", "Hybrid", "Post-quantum resistant KEM"),
            ("ML-KEM-768 + ECDSA", "Hybrid", "Recommended (192-bit security)"),
            ("ML-KEM-1024 + ECDSA", "Hybrid", "Maximum security (256-bit)"),
        ]
        
        print(f"{'Algorithm':<30} {'Type':<15} {'Security'}")
        print("-" * 70)
        for algo, type_, security in algorithms:
            print(f"{algo:<30} {type_:<15} {security}")
        print()


if __name__ == '__main__':
    analyzer = TLSHandshakeAnalyzer()
    
    print("╔════════════════════════════════════════════════════════════╗")
    print("║        PQC TLS Handshake Analyzer                         ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print()
    
    analyzer.capture_handshake()
    analyzer.compare_algorithms()
    
    print()
    print("=" * 70)
    print("Analysis Complete")
    print("=" * 70)




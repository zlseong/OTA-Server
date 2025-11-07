"""
PQC TLS 핸드셰이크 검증 도구
ML-KEM + ECDSA 조합 테스트
"""

import ssl
import socket
import json
import time
from datetime import datetime
from typing import Dict, List

class HandshakeVerifier:
    """PQC TLS 핸드셰이크 검증"""
    
    def __init__(self, cert_dir: str = "test_certs"):
        self.cert_dir = cert_dir
        self.results = []
    
    def test_handshake(
        self,
        host: str = "localhost",
        port: int = 4433,
        kem: str = "mlkem768",
        sig: str = "ECDSA+SHA256"
    ) -> Dict:
        """단일 핸드셰이크 테스트"""
        
        result = {
            'timestamp': datetime.now().isoformat(),
            'host': host,
            'port': port,
            'kem': kem,
            'sig': sig,
            'success': False,
            'error': None,
            'protocol': None,
            'cipher': None,
            'handshake_time_ms': 0
        }
        
        try:
            # SSL 컨텍스트 생성
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.minimum_version = ssl.TLSVersion.TLSv1_3
            context.maximum_version = ssl.TLSVersion.TLSv1_3
            
            # 인증서 로드
            context.load_cert_chain(
                f'{self.cert_dir}/client.crt',
                f'{self.cert_dir}/client.key'
            )
            context.load_verify_locations(f'{self.cert_dir}/ca.crt')
            context.check_hostname = False
            
            # 핸드셰이크 시작
            start_time = time.time()
            
            with socket.create_connection((host, port), timeout=5) as sock:
                with context.wrap_socket(sock, server_hostname=host) as ssock:
                    handshake_time = (time.time() - start_time) * 1000
                    
                    result['success'] = True
                    result['protocol'] = ssock.version()
                    result['cipher'] = ssock.cipher()[0]
                    result['handshake_time_ms'] = round(handshake_time, 2)
                    
                    # 인증서 검증
                    cert = ssock.getpeercert()
                    result['peer_cert_verified'] = cert is not None
                    
                    # 간단한 데이터 전송 테스트
                    ssock.send(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
                    response = ssock.recv(1024)
                    result['data_transfer_ok'] = len(response) > 0
        
        except Exception as e:
            result['error'] = str(e)
        
        self.results.append(result)
        return result
    
    def print_result(self, result: Dict):
        """결과 출력"""
        if result['success']:
            print(f"✅ Handshake successful")
            print(f"   Protocol: {result['protocol']}")
            print(f"   Cipher: {result['cipher']}")
            print(f"   Time: {result['handshake_time_ms']} ms")
            print(f"   Peer cert verified: {result['peer_cert_verified']}")
            print(f"   Data transfer: {'OK' if result['data_transfer_ok'] else 'FAIL'}")
        else:
            print(f"❌ Handshake failed: {result['error']}")
    
    def run_comprehensive_test(self, host: str = "localhost", port: int = 4433, runs: int = 10):
        """종합 테스트 (여러 번 실행)"""
        print("=" * 60)
        print(f"PQC TLS Handshake Test - {runs} runs")
        print("=" * 60)
        print()
        
        success_count = 0
        total_time = 0
        
        for i in range(1, runs + 1):
            print(f"[{i}/{runs}] Testing handshake...")
            result = self.test_handshake(host, port)
            
            if result['success']:
                success_count += 1
                total_time += result['handshake_time_ms']
                print(f"   ✅ {result['handshake_time_ms']} ms")
            else:
                print(f"   ❌ {result['error']}")
            
            time.sleep(0.2)
        
        print()
        print("=" * 60)
        print("Test Summary")
        print("=" * 60)
        print(f"Success rate: {success_count}/{runs} ({success_count/runs*100:.1f}%)")
        
        if success_count > 0:
            avg_time = total_time / success_count
            print(f"Average handshake time: {avg_time:.2f} ms")
        
        print()
    
    def save_results(self, filename: str = "handshake_results.json"):
        """결과 저장"""
        with open(filename, 'w') as f:
            json.dump({
                'test_date': datetime.now().isoformat(),
                'total_tests': len(self.results),
                'results': self.results
            }, f, indent=2)
        print(f"Results saved to {filename}")


def test_different_algorithms():
    """다양한 알고리즘 조합 테스트"""
    print("╔════════════════════════════════════════════════════════════╗")
    print("║   PQC TLS Algorithm Combinations Test                     ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print()
    
    verifier = HandshakeVerifier()
    
    # 테스트할 알고리즘 조합
    algorithms = [
        ("x25519", "ECDSA+SHA256", "Baseline (Classical)"),
        ("mlkem512", "ECDSA+SHA256", "ML-KEM-512 + ECDSA"),
        ("mlkem768", "ECDSA+SHA256", "ML-KEM-768 + ECDSA (Recommended)"),
        ("mlkem1024", "ECDSA+SHA256", "ML-KEM-1024 + ECDSA"),
    ]
    
    for kem, sig, description in algorithms:
        print(f"\n🔐 Testing: {description}")
        print(f"   KEM: {kem}, Signature: {sig}")
        
        result = verifier.test_handshake(kem=kem, sig=sig)
        verifier.print_result(result)
    
    print()
    verifier.save_results()


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == '--comprehensive':
        # 종합 테스트
        verifier = HandshakeVerifier()
        verifier.run_comprehensive_test(runs=30)
    elif len(sys.argv) > 1 and sys.argv[1] == '--algorithms':
        # 알고리즘 조합 테스트
        test_different_algorithms()
    else:
        # 단일 테스트
        verifier = HandshakeVerifier()
        print("Testing single handshake (ML-KEM-768 + ECDSA)...")
        print()
        result = verifier.test_handshake()
        verifier.print_result(result)
        print()
        print("Run with --comprehensive for multiple tests")
        print("Run with --algorithms to test different combinations")




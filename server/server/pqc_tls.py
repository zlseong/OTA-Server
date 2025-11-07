"""
PQC TLS Python Wrapper
C 라이브러리를 ctypes로 호출하는 Python 래퍼
"""

import ctypes
import os
from typing import Optional

# 라이브러리 경로
LIB_PATH = os.path.join(os.path.dirname(__file__), 'libpqc_tls.so')

# ctypes 구조체 정의
class PQCTLSInfo(ctypes.Structure):
    _fields_ = [
        ("protocol", ctypes.c_char * 32),
        ("cipher", ctypes.c_char * 128),
        ("kem", ctypes.c_char * 64),
        ("sig", ctypes.c_char * 64),
        ("peer_cert_verified", ctypes.c_bool)
    ]

class PQCTLSWrapper:
    """PQC TLS C 라이브러리 Python 래퍼"""
    
    def __init__(self, lib_path: str = LIB_PATH):
        """라이브러리 로드"""
        try:
            self.lib = ctypes.CDLL(lib_path)
        except OSError:
            raise RuntimeError(f"Failed to load PQC TLS library: {lib_path}")
        
        self._setup_functions()
        
    def _setup_functions(self):
        """함수 시그니처 설정"""
        # 초기화
        self.lib.pqc_tls_init.argtypes = []
        self.lib.pqc_tls_init.restype = ctypes.c_int
        
        # 정리
        self.lib.pqc_tls_cleanup.argtypes = []
        self.lib.pqc_tls_cleanup.restype = None
        
        # 서버 컨텍스트 생성
        self.lib.pqc_tls_create_server_ctx.argtypes = [
            ctypes.c_char_p,  # cert_file
            ctypes.c_char_p,  # key_file
            ctypes.c_char_p,  # ca_file
            ctypes.c_char_p,  # kem_algorithm
            ctypes.c_char_p,  # sig_algorithm
            ctypes.c_bool     # require_client_cert
        ]
        self.lib.pqc_tls_create_server_ctx.restype = ctypes.c_void_p
        
        # 클라이언트 컨텍스트 생성
        self.lib.pqc_tls_create_client_ctx.argtypes = [
            ctypes.c_char_p,  # cert_file
            ctypes.c_char_p,  # key_file
            ctypes.c_char_p,  # ca_file
            ctypes.c_char_p,  # kem_algorithm
            ctypes.c_char_p   # sig_algorithm
        ]
        self.lib.pqc_tls_create_client_ctx.restype = ctypes.c_void_p
        
        # 컨텍스트 해제
        self.lib.pqc_tls_free_ctx.argtypes = [ctypes.c_void_p]
        self.lib.pqc_tls_free_ctx.restype = None
        
        # 연결 수락
        self.lib.pqc_tls_accept.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.lib.pqc_tls_accept.restype = ctypes.c_void_p
        
        # 연결 시작
        self.lib.pqc_tls_connect.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.lib.pqc_tls_connect.restype = ctypes.c_void_p
        
        # 데이터 읽기
        self.lib.pqc_tls_read.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        self.lib.pqc_tls_read.restype = ctypes.c_int
        
        # 데이터 쓰기
        self.lib.pqc_tls_write.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        self.lib.pqc_tls_write.restype = ctypes.c_int
        
        # 연결 종료
        self.lib.pqc_tls_close.argtypes = [ctypes.c_void_p]
        self.lib.pqc_tls_close.restype = None
        
        # 에러 메시지
        self.lib.pqc_tls_get_error.argtypes = []
        self.lib.pqc_tls_get_error.restype = ctypes.c_char_p
        
        # 연결 정보
        self.lib.pqc_tls_get_info.argtypes = [ctypes.c_void_p, ctypes.POINTER(PQCTLSInfo)]
        self.lib.pqc_tls_get_info.restype = ctypes.c_int
    
    def init(self) -> bool:
        """PQC TLS 초기화"""
        return self.lib.pqc_tls_init() == 0
    
    def cleanup(self):
        """PQC TLS 정리"""
        self.lib.pqc_tls_cleanup()
    
    def create_server_context(
        self,
        cert_file: str,
        key_file: str,
        ca_file: str,
        kem_algorithm: str = "mlkem768",
        sig_algorithm: str = "dilithium3",
        require_client_cert: bool = True
    ) -> Optional[int]:
        """서버 컨텍스트 생성"""
        ctx = self.lib.pqc_tls_create_server_ctx(
            cert_file.encode('utf-8'),
            key_file.encode('utf-8'),
            ca_file.encode('utf-8'),
            kem_algorithm.encode('utf-8'),
            sig_algorithm.encode('utf-8'),
            require_client_cert
        )
        return ctx if ctx else None
    
    def create_client_context(
        self,
        cert_file: str,
        key_file: str,
        ca_file: str,
        kem_algorithm: str = "mlkem768",
        sig_algorithm: str = "dilithium3"
    ) -> Optional[int]:
        """클라이언트 컨텍스트 생성"""
        ctx = self.lib.pqc_tls_create_client_ctx(
            cert_file.encode('utf-8'),
            key_file.encode('utf-8'),
            ca_file.encode('utf-8'),
            kem_algorithm.encode('utf-8'),
            sig_algorithm.encode('utf-8')
        )
        return ctx if ctx else None
    
    def free_context(self, ctx: int):
        """컨텍스트 해제"""
        if ctx:
            self.lib.pqc_tls_free_ctx(ctx)
    
    def accept(self, ctx: int, socket_fd: int) -> Optional[int]:
        """TLS 연결 수락"""
        conn = self.lib.pqc_tls_accept(ctx, socket_fd)
        return conn if conn else None
    
    def connect(self, ctx: int, socket_fd: int) -> Optional[int]:
        """TLS 연결 시작"""
        conn = self.lib.pqc_tls_connect(ctx, socket_fd)
        return conn if conn else None
    
    def read(self, conn: int, size: int = 4096) -> Optional[bytes]:
        """데이터 읽기"""
        buffer = ctypes.create_string_buffer(size)
        n = self.lib.pqc_tls_read(conn, buffer, size)
        if n > 0:
            return buffer.raw[:n]
        return None
    
    def write(self, conn: int, data: bytes) -> int:
        """데이터 쓰기"""
        return self.lib.pqc_tls_write(conn, data, len(data))
    
    def close(self, conn: int):
        """연결 종료"""
        if conn:
            self.lib.pqc_tls_close(conn)
    
    def get_error(self) -> str:
        """에러 메시지 조회"""
        err = self.lib.pqc_tls_get_error()
        return err.decode('utf-8') if err else ""
    
    def get_connection_info(self, conn: int) -> Optional[dict]:
        """연결 정보 조회"""
        info = PQCTLSInfo()
        if self.lib.pqc_tls_get_info(conn, ctypes.byref(info)) == 0:
            return {
                'protocol': info.protocol.decode('utf-8'),
                'cipher': info.cipher.decode('utf-8'),
                'kem': info.kem.decode('utf-8'),
                'sig': info.sig.decode('utf-8'),
                'peer_cert_verified': info.peer_cert_verified
            }
        return None


# 싱글톤 인스턴스
_pqc_tls = None

def get_pqc_tls() -> PQCTLSWrapper:
    """PQC TLS 래퍼 인스턴스 반환"""
    global _pqc_tls
    if _pqc_tls is None:
        _pqc_tls = PQCTLSWrapper()
        _pqc_tls.init()
    return _pqc_tls




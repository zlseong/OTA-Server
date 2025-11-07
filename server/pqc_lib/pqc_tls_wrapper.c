#include "pqc_tls_wrapper.h"
#include <openssl/ssl.h>
#include <openssl/err.h>
#include <stdio.h>
#include <string.h>

static char g_last_error[512] = {0};

// 에러 메시지 저장
static void set_error(const char *msg) {
    snprintf(g_last_error, sizeof(g_last_error), "%s", msg);
    ERR_print_errors_fp(stderr);
}

// 초기화
int pqc_tls_init(void) {
    SSL_load_error_strings();
    OpenSSL_add_ssl_algorithms();
    return 0;
}

// 정리
void pqc_tls_cleanup(void) {
    EVP_cleanup();
    ERR_free_strings();
}

// 서버 컨텍스트 생성
pqc_tls_ctx_t pqc_tls_create_server_ctx(
    const char *cert_file,
    const char *key_file,
    const char *ca_file,
    const char *kem_algorithm,
    const char *sig_algorithm,
    bool require_client_cert
) {
    const SSL_METHOD *method = TLS_server_method();
    SSL_CTX *ctx = SSL_CTX_new(method);
    
    if (!ctx) {
        set_error("Failed to create SSL context");
        return NULL;
    }
    
    // TLS 1.3만 사용
    SSL_CTX_set_min_proto_version(ctx, TLS1_3_VERSION);
    SSL_CTX_set_max_proto_version(ctx, TLS1_3_VERSION);
    
    // Cipher suite
    if (SSL_CTX_set_ciphersuites(ctx, "TLS_AES_128_GCM_SHA256") != 1) {
        set_error("Failed to set cipher suite");
        SSL_CTX_free(ctx);
        return NULL;
    }
    
    // KEM 설정
    if (kem_algorithm && SSL_CTX_set1_groups_list(ctx, kem_algorithm) != 1) {
        fprintf(stderr, "[WARN] Failed to set KEM: %s\n", kem_algorithm);
    }
    
    // 서명 알고리즘 설정
    if (sig_algorithm && SSL_CTX_set1_sigalgs_list(ctx, sig_algorithm) != 1) {
        fprintf(stderr, "[WARN] Failed to set signature: %s\n", sig_algorithm);
    }
    
    // 인증서 로드
    if (SSL_CTX_use_certificate_file(ctx, cert_file, SSL_FILETYPE_PEM) <= 0) {
        set_error("Failed to load certificate");
        SSL_CTX_free(ctx);
        return NULL;
    }
    
    // 개인키 로드
    if (SSL_CTX_use_PrivateKey_file(ctx, key_file, SSL_FILETYPE_PEM) <= 0) {
        set_error("Failed to load private key");
        SSL_CTX_free(ctx);
        return NULL;
    }
    
    // mTLS 설정
    if (require_client_cert) {
        SSL_CTX_set_verify(ctx, SSL_VERIFY_PEER | SSL_VERIFY_FAIL_IF_NO_PEER_CERT, NULL);
        
        if (ca_file && SSL_CTX_load_verify_locations(ctx, ca_file, NULL) != 1) {
            set_error("Failed to load CA certificate");
            SSL_CTX_free(ctx);
            return NULL;
        }
    }
    
    return (pqc_tls_ctx_t)ctx;
}

// 클라이언트 컨텍스트 생성
pqc_tls_ctx_t pqc_tls_create_client_ctx(
    const char *cert_file,
    const char *key_file,
    const char *ca_file,
    const char *kem_algorithm,
    const char *sig_algorithm
) {
    const SSL_METHOD *method = TLS_client_method();
    SSL_CTX *ctx = SSL_CTX_new(method);
    
    if (!ctx) {
        set_error("Failed to create SSL context");
        return NULL;
    }
    
    // TLS 1.3만 사용
    SSL_CTX_set_min_proto_version(ctx, TLS1_3_VERSION);
    SSL_CTX_set_max_proto_version(ctx, TLS1_3_VERSION);
    
    // Cipher suite
    if (SSL_CTX_set_ciphersuites(ctx, "TLS_AES_128_GCM_SHA256") != 1) {
        set_error("Failed to set cipher suite");
        SSL_CTX_free(ctx);
        return NULL;
    }
    
    // KEM 설정
    if (kem_algorithm && SSL_CTX_set1_groups_list(ctx, kem_algorithm) != 1) {
        fprintf(stderr, "[WARN] Failed to set KEM: %s\n", kem_algorithm);
    }
    
    // 서명 알고리즘 설정
    if (sig_algorithm && SSL_CTX_set1_sigalgs_list(ctx, sig_algorithm) != 1) {
        fprintf(stderr, "[WARN] Failed to set signature: %s\n", sig_algorithm);
    }
    
    // 클라이언트 인증서 (mTLS용)
    if (cert_file && SSL_CTX_use_certificate_file(ctx, cert_file, SSL_FILETYPE_PEM) <= 0) {
        set_error("Failed to load client certificate");
        SSL_CTX_free(ctx);
        return NULL;
    }
    
    if (key_file && SSL_CTX_use_PrivateKey_file(ctx, key_file, SSL_FILETYPE_PEM) <= 0) {
        set_error("Failed to load client private key");
        SSL_CTX_free(ctx);
        return NULL;
    }
    
    // 서버 인증서 검증
    SSL_CTX_set_verify(ctx, SSL_VERIFY_PEER, NULL);
    
    if (ca_file && SSL_CTX_load_verify_locations(ctx, ca_file, NULL) != 1) {
        set_error("Failed to load CA certificate");
        SSL_CTX_free(ctx);
        return NULL;
    }
    
    return (pqc_tls_ctx_t)ctx;
}

// 컨텍스트 해제
void pqc_tls_free_ctx(pqc_tls_ctx_t ctx) {
    if (ctx) {
        SSL_CTX_free((SSL_CTX*)ctx);
    }
}

// 서버 연결 수락
pqc_tls_conn_t pqc_tls_accept(pqc_tls_ctx_t ctx, int socket_fd) {
    SSL *ssl = SSL_new((SSL_CTX*)ctx);
    if (!ssl) {
        set_error("Failed to create SSL object");
        return NULL;
    }
    
    SSL_set_fd(ssl, socket_fd);
    
    if (SSL_accept(ssl) <= 0) {
        set_error("SSL handshake failed");
        SSL_free(ssl);
        return NULL;
    }
    
    return (pqc_tls_conn_t)ssl;
}

// 클라이언트 연결
pqc_tls_conn_t pqc_tls_connect(pqc_tls_ctx_t ctx, int socket_fd) {
    SSL *ssl = SSL_new((SSL_CTX*)ctx);
    if (!ssl) {
        set_error("Failed to create SSL object");
        return NULL;
    }
    
    SSL_set_fd(ssl, socket_fd);
    
    if (SSL_connect(ssl) <= 0) {
        set_error("SSL handshake failed");
        SSL_free(ssl);
        return NULL;
    }
    
    return (pqc_tls_conn_t)ssl;
}

// 데이터 읽기
int pqc_tls_read(pqc_tls_conn_t conn, char *buffer, int size) {
    if (!conn) return -1;
    return SSL_read((SSL*)conn, buffer, size);
}

// 데이터 쓰기
int pqc_tls_write(pqc_tls_conn_t conn, const char *buffer, int size) {
    if (!conn) return -1;
    return SSL_write((SSL*)conn, buffer, size);
}

// 연결 종료
void pqc_tls_close(pqc_tls_conn_t conn) {
    if (conn) {
        SSL_shutdown((SSL*)conn);
        SSL_free((SSL*)conn);
    }
}

// 에러 메시지 반환
const char* pqc_tls_get_error(void) {
    return g_last_error;
}

// 연결 정보 조회
int pqc_tls_get_info(pqc_tls_conn_t conn, pqc_tls_info_t *info) {
    if (!conn || !info) return -1;
    
    SSL *ssl = (SSL*)conn;
    
    strncpy(info->protocol, SSL_get_version(ssl), sizeof(info->protocol) - 1);
    strncpy(info->cipher, SSL_get_cipher(ssl), sizeof(info->cipher) - 1);
    
    X509 *cert = SSL_get_peer_certificate(ssl);
    info->peer_cert_verified = (cert != NULL);
    if (cert) X509_free(cert);
    
    // KEM, SIG는 OpenSSL 3.x API로 조회 가능 (생략)
    strcpy(info->kem, "N/A");
    strcpy(info->sig, "N/A");
    
    return 0;
}




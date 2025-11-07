#ifndef PQC_TLS_WRAPPER_H
#define PQC_TLS_WRAPPER_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

// PQC TLS 컨텍스트 핸들
typedef void* pqc_tls_ctx_t;
typedef void* pqc_tls_conn_t;

// 초기화 및 정리
int pqc_tls_init(void);
void pqc_tls_cleanup(void);

// 컨텍스트 생성
pqc_tls_ctx_t pqc_tls_create_server_ctx(
    const char *cert_file,
    const char *key_file,
    const char *ca_file,
    const char *kem_algorithm,
    const char *sig_algorithm,
    bool require_client_cert
);

pqc_tls_ctx_t pqc_tls_create_client_ctx(
    const char *cert_file,
    const char *key_file,
    const char *ca_file,
    const char *kem_algorithm,
    const char *sig_algorithm
);

// 컨텍스트 해제
void pqc_tls_free_ctx(pqc_tls_ctx_t ctx);

// 연결 생성
pqc_tls_conn_t pqc_tls_accept(pqc_tls_ctx_t ctx, int socket_fd);
pqc_tls_conn_t pqc_tls_connect(pqc_tls_ctx_t ctx, int socket_fd);

// 데이터 송수신
int pqc_tls_read(pqc_tls_conn_t conn, char *buffer, int size);
int pqc_tls_write(pqc_tls_conn_t conn, const char *buffer, int size);

// 연결 종료
void pqc_tls_close(pqc_tls_conn_t conn);

// 에러 처리
const char* pqc_tls_get_error(void);

// 연결 정보
typedef struct {
    char protocol[32];
    char cipher[128];
    char kem[64];
    char sig[64];
    bool peer_cert_verified;
} pqc_tls_info_t;

int pqc_tls_get_info(pqc_tls_conn_t conn, pqc_tls_info_t *info);

#ifdef __cplusplus
}
#endif

#endif // PQC_TLS_WRAPPER_H




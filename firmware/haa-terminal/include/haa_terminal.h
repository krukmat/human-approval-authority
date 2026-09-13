#pragma once

#include <stddef.h>
#include <stdint.h>

typedef enum {
    HAA_TERMINAL_BOOTING = 0,
    HAA_TERMINAL_IDLE,
    HAA_TERMINAL_PACKAGE_RECEIVED,
    HAA_TERMINAL_PACKAGE_VERIFIED,
    HAA_TERMINAL_AWAITING_HUMAN,
    HAA_TERMINAL_APPROVED,
    HAA_TERMINAL_REJECTED,
    HAA_TERMINAL_ERROR,
} haa_terminal_state_t;

/**
 * W5-T01 contract boundary only.
 *
 * No biometric, display, transport or signing implementation belongs here yet.
 * Later tasks must preserve the security ordering:
 *
 * receive exact signed package bytes
 *   -> verify HAA signature
 *   -> render trusted claims
 *   -> local human verification
 *   -> sign ApprovalEvidence
 */
const char *haa_terminal_state_name(haa_terminal_state_t state);

/** Maximum envelope size accepted by the POC transport layer (W5-T02). */
#define HAA_TERMINAL_MAX_PACKAGE_BYTES 4096U

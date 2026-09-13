#include "haa_terminal.h"

#include "esp_chip_info.h"
#include "esp_log.h"
#include "esp_system.h"

static const char *TAG = "haa-terminal";

const char *haa_terminal_state_name(haa_terminal_state_t state) {
    switch (state) {
        case HAA_TERMINAL_BOOTING: return "BOOTING";
        case HAA_TERMINAL_IDLE: return "IDLE";
        case HAA_TERMINAL_PACKAGE_RECEIVED: return "PACKAGE_RECEIVED";
        case HAA_TERMINAL_PACKAGE_VERIFIED: return "PACKAGE_VERIFIED";
        case HAA_TERMINAL_AWAITING_HUMAN: return "AWAITING_HUMAN";
        case HAA_TERMINAL_APPROVED: return "APPROVED";
        case HAA_TERMINAL_REJECTED: return "REJECTED";
        case HAA_TERMINAL_ERROR: return "ERROR";
        default: return "UNKNOWN";
    }
}

void app_main(void) {
    esp_chip_info_t chip_info;
    esp_chip_info(&chip_info);

    const haa_terminal_state_t state = HAA_TERMINAL_IDLE;

    ESP_LOGI(TAG, "Human Approval Authority terminal POC scaffold");
    ESP_LOGI(TAG, "target cores=%d revision=%d", chip_info.cores, chip_info.revision);
    ESP_LOGI(TAG, "state=%s", haa_terminal_state_name(state));
    ESP_LOGI(TAG, "W5-T02 will add USB challenge transport + signature verification");
    ESP_LOGI(TAG, "Wi-Fi/Bluetooth application transports are intentionally out of scope for v0.x");
}

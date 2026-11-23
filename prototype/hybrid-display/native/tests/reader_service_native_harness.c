/* Test-only Fake-ABI. No environment, native FD, socket, path or bus operations. */
#include "reader_service_native.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct scenario {
    const char *name;
    unsigned metadata, fault;
    enum hd_reason expected;
    unsigned takes, inspections, handoffs, releases;
};
struct fake {
    unsigned fault, takes, inspections, handoffs, releases;
    int owned, consumed, phase_ok;
    uint64_t time;
    struct hd_abi *source;
};

static struct hd_metadata metadata(unsigned mode)
{
    struct hd_metadata value = {{'4','1'}, 2, {'1'}, 1, 41, 1, 1, 2, 0};
    if (mode == 1) value.pid_present = 0;
    if (mode == 2) value.current_pid = 42;
    if (mode == 3) value.pid[0] = (unsigned char)'x';
    if (mode == 4) value.count_present = 0;
    if (mode == 5) value.count[0] = (unsigned char)'0';
    if (mode == 6) value.count[0] = (unsigned char)'2';
    if (mode == 7) value.unknown_fields = 1;
    if (mode == 8) value.pid_length = 11;
    if (mode == 9) { (void)memcpy(value.pid, "2147483648", 10); value.pid_length = 10; }
    if (mode == 10) value.pid[0] = (unsigned char)'0';
    if (mode == 11) value.count_length = 2;
    if (mode == 12) value.pid[1] = 0;
    if (mode == 13) value.count[0] = (unsigned char)'x';
    if (mode == 14) value.field_count = 3;
    if (mode == 15) value.pid_present = 2;
    if (mode == 16) value.current_pid = 0;
    return value;
}
static enum hd_call fake_now(void *context, uint64_t *value)
{
    struct fake *fake = context;
    if (fake->fault == 26) return HD_CALL_ERROR;
    if (fake->fault == 36) return (enum hd_call)99;
    *value = fake->time;
    return HD_CALL_OK;
}
static enum hd_call fake_take(void *context, uint32_t descriptor, struct hd_receipt *receipt)
{
    struct fake *fake = context;
    ++fake->takes;
    if (descriptor != HD_ACTIVATION_FD || fake->owned || fake->consumed)
        return HD_CALL_REJECTED;
    if (fake->fault == 1) return HD_CALL_REJECTED;
    if (fake->fault == 21) { fake->time += HD_SERVICE_NS; return HD_CALL_REJECTED; }
    if (fake->fault == 2) return HD_CALL_ERROR;
    if (fake->fault == 3) return HD_CALL_TIMEOUT;
    if (fake->fault == 4) return (enum hd_call)99;
    *receipt = (struct hd_receipt){HD_RECEIPT_TAG, HD_ACTIVATION_FD, 1};
    if (fake->fault == 5) receipt->descriptor = 4;
    if (fake->fault == 6) receipt->tag = 0;
    if (fake->fault == 7) receipt->generation = 0;
    if (fake->fault == 35) receipt->generation = UINT64_MAX;
    /* Malformed confirmation transfers nothing under the atomic ABI. */
    if ((fake->fault >= 5 && fake->fault <= 7) || fake->fault == 35) return HD_CALL_OK;
    fake->owned = 1;
    if (fake->fault == 20) fake->time += HD_SERVICE_NS;
    if (fake->fault == 25) fake->time = 0;
    if (fake->fault == 39) {
        fake->source->release = NULL;
        fake->source->now = NULL;
    }
    return HD_CALL_OK;
}
static enum hd_call fake_inspect(void *context, const struct hd_receipt *receipt,
                                 struct hd_descriptor *value)
{
    struct fake *fake = context;
    ++fake->inspections;
    if (!fake->owned || receipt->descriptor != HD_ACTIVATION_FD) return HD_CALL_ERROR;
    *value = (struct hd_descriptor){3, 1, 1, 1, 1, 0, 1, 1, 1, 2};
    if (fake->fault == 8) value->family = 2;
    if (fake->fault == 9) value->kind = 2;
    if (fake->fault == 10) value->listening = 0;
    if (fake->fault == 11) value->connected = 1;
    if (fake->fault == 12) value->valid = 0;
    if (fake->fault == 13) value->descriptor = 4;
    if (fake->fault == 14) value->nonblocking = 0;
    if (fake->fault == 15) value->cloexec = 0;
    if (fake->fault == 16) return HD_CALL_ERROR;
    if (fake->fault == 17) return (enum hd_call)99;
    if (fake->fault == 22) fake->time += HD_SERVICE_NS;
    return HD_CALL_OK;
}
static enum hd_call fake_release(void *context, const struct hd_receipt *receipt)
{
    struct fake *fake = context;
    ++fake->releases;
    if (!fake->owned || fake->consumed || receipt->descriptor != HD_ACTIVATION_FD)
        return HD_CALL_ERROR;
    fake->owned = 0;
    fake->consumed = 1;
    if (fake->fault == 24) fake->time += HD_SERVICE_NS;
    if (fake->fault == 28) return HD_CALL_ERROR;
    if (fake->fault == 29) return (enum hd_call)99;
    if (fake->fault == 31) return HD_CALL_REJECTED;
    return HD_CALL_OK;
}
static enum hd_reason fake_handoff(void *context, struct hd_owner *owner,
                                   const struct hd_descriptor *descriptor, uint64_t deadline)
{
    struct fake *fake = context;
    enum hd_reason reason;
    ++fake->handoffs;
    fake->phase_ok = hd_owner_phase(owner) == HD_TRANSFERRED;
    if (descriptor->descriptor != HD_ACTIVATION_FD || deadline != UINT64_C(5000000000))
        return HD_READER_FAILED;
    if (fake->fault == 18) return HD_READER_FAILED;
    if (fake->fault == 19) return (enum hd_reason)99;
    if (fake->fault == 41) return (enum hd_reason)-1;
    if (fake->fault == 40 && (hd_owner_phase(NULL) != HD_UNOWNED
        || hd_owner_release(NULL) != HD_INPUT_INVALID)) return HD_READER_FAILED;
    if (fake->fault == 23) fake->time += HD_SERVICE_NS;
    reason = hd_owner_release(owner);
    fake->phase_ok = fake->phase_ok && hd_owner_phase(owner) == HD_CLOSED;
    if (fake->fault == 30 && hd_owner_release(owner) != HD_OK) return HD_READER_FAILED;
    return reason;
}

static const struct scenario cases[] = {
    {"missing_pid", 1, 0, HD_INPUT_INVALID, 0, 0, 0, 0},
    {"valid", 0, 0, HD_OK, 1, 1, 1, 1},
    {"take_rejected", 0, 1, HD_SOURCE_NOT_ALLOWED, 1, 0, 0, 0},
    {"runtime_error", 0, 18, HD_READER_FAILED, 1, 1, 1, 1},
    {"double_close", 0, 30, HD_OK, 1, 1, 1, 1}
    ,{"pid_mismatch", 2, 0, HD_INPUT_INVALID, 0, 0, 0, 0}
    ,{"pid_syntax", 3, 0, HD_INPUT_INVALID, 0, 0, 0, 0}
    ,{"missing_count", 4, 0, HD_INPUT_INVALID, 0, 0, 0, 0}
    ,{"zero_count", 5, 0, HD_INPUT_INVALID, 0, 0, 0, 0}
    ,{"multiple_count", 6, 0, HD_INPUT_INVALID, 0, 0, 0, 0}
    ,{"unknown_fields", 7, 0, HD_INPUT_INVALID, 0, 0, 0, 0}
    ,{"pid_length", 8, 0, HD_INPUT_INVALID, 0, 0, 0, 0}
    ,{"pid_overflow", 9, 0, HD_INPUT_INVALID, 0, 0, 0, 0}
    ,{"pid_noncanonical", 10, 0, HD_INPUT_INVALID, 0, 0, 0, 0}
    ,{"count_syntax", 11, 0, HD_INPUT_INVALID, 0, 0, 0, 0}
    ,{"take_error", 0, 2, HD_READER_FAILED, 1, 0, 0, 0}
    ,{"take_timeout", 0, 3, HD_SOURCE_TIMEOUT, 1, 0, 0, 0}
    ,{"take_unknown", 0, 4, HD_READER_FAILED, 1, 0, 0, 0}
    ,{"receipt_fd", 0, 5, HD_SOURCE_NOT_ALLOWED, 1, 0, 0, 0}
    ,{"receipt_tag", 0, 6, HD_SOURCE_NOT_ALLOWED, 1, 0, 0, 0}
    ,{"receipt_generation", 0, 7, HD_SOURCE_NOT_ALLOWED, 1, 0, 0, 0}
    ,{"family", 0, 8, HD_SOURCE_NOT_ALLOWED, 1, 1, 0, 1}
    ,{"type", 0, 9, HD_SOURCE_NOT_ALLOWED, 1, 1, 0, 1}
    ,{"listening", 0, 10, HD_SOURCE_NOT_ALLOWED, 1, 1, 0, 1}
    ,{"connected", 0, 11, HD_SOURCE_NOT_ALLOWED, 1, 1, 0, 1}
    ,{"closed", 0, 12, HD_SOURCE_NOT_ALLOWED, 1, 1, 0, 1}
    ,{"descriptor_fd", 0, 13, HD_SOURCE_NOT_ALLOWED, 1, 1, 0, 1}
    ,{"nonblocking", 0, 14, HD_SOURCE_NOT_ALLOWED, 1, 1, 0, 1}
    ,{"cloexec", 0, 15, HD_SOURCE_NOT_ALLOWED, 1, 1, 0, 1}
    ,{"inspect_error", 0, 16, HD_READER_FAILED, 1, 1, 0, 1}
    ,{"inspect_unknown", 0, 17, HD_READER_FAILED, 1, 1, 0, 1}
    ,{"runtime_unknown", 0, 19, HD_READER_FAILED, 1, 1, 1, 1}
    ,{"take_late", 0, 20, HD_SOURCE_TIMEOUT, 1, 0, 0, 1}
    ,{"unconfirmed_late", 0, 21, HD_SOURCE_TIMEOUT, 1, 0, 0, 0}
    ,{"inspect_late", 0, 22, HD_SOURCE_TIMEOUT, 1, 1, 0, 1}
    ,{"runtime_late", 0, 23, HD_SOURCE_TIMEOUT, 1, 1, 1, 1}
    ,{"cleanup_late", 0, 24, HD_SOURCE_TIMEOUT, 1, 1, 1, 1}
    ,{"clock_backwards", 0, 25, HD_READER_FAILED, 1, 0, 0, 1}
    ,{"clock_error", 0, 26, HD_READER_FAILED, 0, 0, 0, 0}
    ,{"clock_overflow", 0, 27, HD_READER_FAILED, 0, 0, 0, 0}
    ,{"release_error", 0, 28, HD_READER_FAILED, 1, 1, 1, 1}
    ,{"release_unknown", 0, 29, HD_READER_FAILED, 1, 1, 1, 1}
    ,{"null_abi", 0, 32, HD_SOURCE_UNAVAILABLE, 0, 0, 0, 0}
    ,{"incomplete_abi", 0, 33, HD_SOURCE_UNAVAILABLE, 0, 0, 0, 0}
    ,{"abi_version", 0, 34, HD_SOURCE_UNAVAILABLE, 0, 0, 0, 0}
    ,{"clock_unknown", 0, 36, HD_READER_FAILED, 0, 0, 0, 0}
    ,{"consumed_token", 0, 37, HD_SOURCE_NOT_ALLOWED, 1, 0, 0, 0}
    ,{"null_metadata", 99, 0, HD_INPUT_INVALID, 0, 0, 0, 0}
    ,{"release_rejected", 0, 31, HD_READER_FAILED, 1, 1, 1, 1}
    ,{"generation_overflow", 0, 35, HD_SOURCE_NOT_ALLOWED, 1, 0, 0, 0}
    ,{"repeat_consumed_token", 0, 38, HD_SOURCE_NOT_ALLOWED, 2, 1, 1, 1}
    ,{"abi_snapshot", 0, 39, HD_OK, 1, 1, 1, 1}
    ,{"null_owner", 0, 40, HD_OK, 1, 1, 1, 1}
    ,{"negative_runtime_code", 0, 41, HD_READER_FAILED, 1, 1, 1, 1}
    ,{"pid_nul", 12, 0, HD_INPUT_INVALID, 0, 0, 0, 0}
    ,{"count_nondigit", 13, 0, HD_INPUT_INVALID, 0, 0, 0, 0}
    ,{"extra_field", 14, 0, HD_INPUT_INVALID, 0, 0, 0, 0}
    ,{"invalid_presence", 15, 0, HD_INPUT_INVALID, 0, 0, 0, 0}
    ,{"zero_current_pid", 16, 0, HD_INPUT_INVALID, 0, 0, 0, 0}
};

int main(void)
{
    size_t i;
    int failed = 0;
    for (i = 0; i < sizeof cases / sizeof cases[0]; ++i) {
        const struct scenario *test = &cases[i];
        struct fake fake = {0};
        struct hd_metadata input = metadata(test->metadata);
        struct hd_abi abi = {HD_ABI_VERSION, &fake, fake_now, fake_take,
                            fake_inspect, fake_handoff, fake_release};
        struct hd_result result;
        fake.fault = test->fault;
        fake.source = &abi;
        fake.time = UINT64_C(1000000000);
        if (fake.fault == 27) fake.time = UINT64_MAX;
        if (fake.fault == 33) abi.inspect = NULL;
        if (fake.fault == 34) abi.version = 2;
        if (fake.fault == 37) fake.consumed = 1;
        result = hd_run(test->metadata == 99 ? NULL : &input, fake.fault == 32 ? NULL : &abi);
        if (fake.fault == 38) {
            if (result.reason != HD_OK || fake.owned || !fake.consumed) failed = 1;
            result = hd_run(&input, &abi);
        }
        if (result.reason != test->expected || fake.takes != test->takes
            || fake.inspections != test->inspections || fake.handoffs != test->handoffs
            || fake.releases != test->releases || fake.owned
            || (fake.handoffs && !fake.phase_ok)) {
            (void)printf("FAIL %s\n", test->name);
            failed = 1;
        }
        /* Shared synthetic variants, fixed codes and event counts only. */
        (void)printf("CASE %s %u %u %u %u %u %u %u\n", test->name,
            test->metadata, test->fault, (unsigned)result.reason, fake.takes,
            fake.inspections, fake.handoffs, fake.releases);
    }
    (void)printf("CASES %zu %s\n", sizeof cases / sizeof cases[0], failed ? "FAIL" : "OK");
    return failed ? EXIT_FAILURE : EXIT_SUCCESS;
}

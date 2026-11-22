#include "reader_service_native.h"

struct hd_owner {
    enum hd_phase phase;
    struct hd_receipt receipt;
    struct hd_abi abi;
};

struct budget {
    uint64_t last, deadline;
    int started;
    enum hd_reason failure;
};

static enum hd_reason check_budget(struct budget *budget, const struct hd_abi *abi)
{
    uint64_t now = 0;
    if (budget->failure != HD_OK) return budget->failure;
    if (abi->now(abi->context, &now) != HD_CALL_OK
        || (!budget->started && now > UINT64_MAX - HD_SERVICE_NS)
        || (budget->started && now < budget->last)) {
        budget->failure = HD_READER_FAILED;
    } else {
        if (!budget->started) {
            budget->deadline = now + HD_SERVICE_NS;
            budget->started = 1;
        }
        budget->last = now;
        if (now >= budget->deadline) budget->failure = HD_SOURCE_TIMEOUT;
    }
    return budget->failure;
}

static enum hd_reason call_reason(enum hd_call code)
{
    switch (code) {
    case HD_CALL_OK: return HD_OK;
    case HD_CALL_REJECTED: return HD_SOURCE_NOT_ALLOWED;
    case HD_CALL_TIMEOUT: return HD_SOURCE_TIMEOUT;
    default: return HD_READER_FAILED;
    }
}

enum hd_phase hd_owner_phase(const struct hd_owner *owner)
{
    return owner == NULL ? HD_UNOWNED : owner->phase;
}

enum hd_reason hd_owner_release(struct hd_owner *owner)
{
    if (owner == NULL) return HD_INPUT_INVALID;
    if (owner->phase == HD_CLOSED) return HD_OK;
    if (owner->phase != HD_TRANSFERRED) return HD_SOURCE_NOT_ALLOWED;
    owner->phase = HD_CLOSED;
    return owner->abi.release(owner->abi.context, &owner->receipt) == HD_CALL_OK
        ? HD_OK : HD_READER_FAILED;
}

static int metadata_valid(const struct hd_metadata *value)
{
    uint32_t pid = 0;
    size_t i;
    if (value == NULL || value->pid_present != 1 || value->count_present != 1
        || value->field_count != 2 || value->unknown_fields != 0
        || value->pid_length == 0 || value->pid_length > sizeof value->pid
        || value->count_length != 1 || value->count[0] != (unsigned char)'1'
        || value->pid[0] == (unsigned char)'0' || value->current_pid == 0
        || value->current_pid > INT32_MAX) {
        return 0;
    }
    for (i = 0; i < value->pid_length; ++i) {
        uint32_t digit;
        if (value->pid[i] < (unsigned char)'0' || value->pid[i] > (unsigned char)'9') {
            return 0;
        }
        digit = (uint32_t)(value->pid[i] - (unsigned char)'0');
        if (pid > ((uint32_t)INT32_MAX - digit) / UINT32_C(10)) {
            return 0;
        }
        pid = pid * UINT32_C(10) + digit;
    }
    return pid == value->current_pid;
}

static int receipt_valid(const struct hd_receipt *value)
{
    return value->tag == HD_RECEIPT_TAG && value->descriptor == HD_ACTIVATION_FD
        && value->generation > 0 && value->generation <= INT64_MAX;
}

static int descriptor_valid(const struct hd_descriptor *value)
{
    return value->descriptor == HD_ACTIVATION_FD && value->family == 1
        && value->kind == 1 && value->valid == 1 && value->listening == 1
        && value->connected == 0 && value->nonblocking == 1 && value->cloexec == 1;
}

struct hd_result hd_run(const struct hd_metadata *metadata, const struct hd_abi *abi)
{
    struct hd_result result = { HD_SOURCE_UNAVAILABLE };
    struct hd_owner owner = {0};
    struct hd_descriptor descriptor = {0};
    struct budget budget = {0};
    enum hd_call code;
    if (!metadata_valid(metadata)) {
        result.reason = HD_INPUT_INVALID;
        return result;
    }
    if (abi == NULL || abi->version != HD_ABI_VERSION || abi->now == NULL
        || abi->take == NULL || abi->inspect == NULL || abi->handoff == NULL
        || abi->release == NULL) return result;
    owner.abi = *abi;
    result.reason = check_budget(&budget, &owner.abi);
    if (result.reason != HD_OK) return result;
    code = owner.abi.take(owner.abi.context, HD_ACTIVATION_FD, &owner.receipt);
    result.reason = call_reason(code);
    if (code == HD_CALL_OK) {
        if (receipt_valid(&owner.receipt)) owner.phase = HD_OWNED;
        else result.reason = HD_SOURCE_NOT_ALLOWED;
    }
    if (check_budget(&budget, &owner.abi) != HD_OK) result.reason = budget.failure;
    if (result.reason != HD_OK) goto cleanup;
    code = owner.abi.inspect(owner.abi.context, &owner.receipt, &descriptor);
    result.reason = call_reason(code);
    if (check_budget(&budget, &owner.abi) != HD_OK) result.reason = budget.failure;
    if (result.reason == HD_OK && !descriptor_valid(&descriptor))
        result.reason = HD_SOURCE_NOT_ALLOWED;
    if (result.reason == HD_OK) {
        owner.phase = HD_TRANSFERRED;
        result.reason = owner.abi.handoff(owner.abi.context, &owner, &descriptor, budget.deadline);
        if ((unsigned)result.reason > (unsigned)HD_KSCREEN_SCHEMA_INVALID)
            result.reason = HD_READER_FAILED;
    }
cleanup:
    if (owner.phase == HD_OWNED || owner.phase == HD_TRANSFERRED) {
        enum hd_reason cleanup;
        owner.phase = HD_CLOSED;
        cleanup = call_reason(owner.abi.release(owner.abi.context, &owner.receipt));
        if (cleanup != HD_OK) result.reason = HD_READER_FAILED;
    }
    if (check_budget(&budget, &owner.abi) != HD_OK) result.reason = budget.failure;
    return result;
}

#ifndef READER_SERVICE_NATIVE_H
#define READER_SERVICE_NATIVE_H
#include <stddef.h>
#include <stdint.h>

/* Reference core only. No entrypoint, native FD acquisition or OS integration.
 * All input/ABI pointers must designate live, readable C objects; C cannot
 * authenticate an arbitrary pointer or sandbox an injected function pointer.
 * Inputs/ABI remain alive and immutable through hd_run. The ABI is copied before
 * callbacks. Callbacks are trusted code and must terminate within the supplied
 * cooperative budget; no hard native interruption is implemented here.
 *
 * take is atomic: anything except OK plus a valid tagged receipt transfers NO
 * resource. A valid receipt pins exactly FD3 and its generation through release.
 * The adapter rejects already consumed receipts, including across hd_run calls;
 * a tag is not authority or cryptographic/systemd evidence. No global registry
 * or descriptor discovery lives in this core. release consumes ownership even
 * when reporting an error. handoff borrows an opaque owner only for the callback
 * lifetime, may release it once/idempotently, and must not retain/copy its address.
 * Core cleanup is a runtime-owner guard after transfer, never a second owner.
 *
 * Timestamps are unsigned nanoseconds. Starts above UINT64_MAX-4s fail closed
 * before acquisition (a deliberately narrower representable domain than Python).
 * All overflow/clock failures use reader_failed; expiry uses source_timeout.
 * Same-UID authority, real adapters, sandbox, packaging and D-Bus remain open.
 */
#define HD_ACTIVATION_FD UINT32_C(3)
#define HD_RECEIPT_TAG UINT32_C(0x48445231)
#define HD_ABI_VERSION UINT32_C(1)
#define HD_SERVICE_NS UINT64_C(4000000000)

enum hd_reason {
    HD_OK = 0, HD_INPUT_INVALID = 1, HD_SOURCE_NOT_ALLOWED = 2,
    HD_SOURCE_UNAVAILABLE = 3, HD_SOURCE_DENIED = 4, HD_SOURCE_LIMIT = 5,
    HD_SOURCE_TIMEOUT = 6, HD_SOURCE_TYPE_INVALID = 7, HD_IPC_INVALID = 8,
    HD_IPC_LIMIT = 9, HD_OWNER_MISSING = 10, HD_OWNER_INVALID = 11,
    HD_SESSION_UNVERIFIED = 12, HD_INVENTORY_CHANGED = 13,
    HD_KSCREEN_PROFILE_UNVERIFIED = 14, HD_CLIENT_INVENTORY_UNVERIFIED = 15,
    HD_READER_DEADLINE_UNVERIFIED = 16, HD_READER_FAILED = 17,
    HD_EDID_INVALID = 18, HD_KSCREEN_UNAVAILABLE = 19, HD_KSCREEN_SCHEMA_INVALID = 20
};
enum hd_phase { HD_UNOWNED, HD_OWNED, HD_TRANSFERRED, HD_CLOSED };
enum hd_call { HD_CALL_OK, HD_CALL_REJECTED, HD_CALL_ERROR, HD_CALL_TIMEOUT };
struct hd_metadata {
    unsigned char pid[10];
    size_t pid_length;
    unsigned char count[2];
    size_t count_length;
    uint32_t current_pid;
    uint8_t pid_present, count_present, field_count, unknown_fields;
};
struct hd_receipt { uint32_t tag, descriptor; uint64_t generation; };
struct hd_descriptor {
    uint32_t descriptor, family, kind; /* family=1 Unix, kind=1 stream */
    uint8_t valid, listening, connected, nonblocking, cloexec;
    uint64_t device, inode;
};
struct hd_result { enum hd_reason reason; }; /* No raw metadata or handles. */
struct hd_owner;
struct hd_abi {
    uint32_t version;
    void *context;
    enum hd_call (*now)(void *, uint64_t *);
    enum hd_call (*take)(void *, uint32_t, struct hd_receipt *);
    enum hd_call (*inspect)(void *, const struct hd_receipt *, struct hd_descriptor *);
    enum hd_reason (*handoff)(void *, struct hd_owner *, const struct hd_descriptor *, uint64_t);
    enum hd_call (*release)(void *, const struct hd_receipt *);
};

struct hd_result hd_run(const struct hd_metadata *, const struct hd_abi *);
enum hd_phase hd_owner_phase(const struct hd_owner *);
enum hd_reason hd_owner_release(struct hd_owner *);
#endif

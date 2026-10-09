/*
 * vulkan_device_gate.c - one-command Detroit Vulkan device gate for Madeira.
 *
 * This x86-64 Windows program runs the three existing Vulkan canaries through
 * the same Wine/FEX child-process path used by real Windows software on iOS.
 * It stops at the first failed or hung stage and prints a small, stable summary
 * that can be copied directly from madeira-log.txt.
 *
 * A durable proof file is deliberately written by THIS x86-64 Windows process,
 * not by the iOS UI. The previous proof is deleted before any test runs, and a
 * new proof appears only after all three child canaries return success.
 *
 * The proof also fingerprints the exact four x64 Windows binaries used by this
 * gate. Madeira recomputes the same fingerprint from the test payload bundled
 * in the currently installed app. A proof from an older renderer/test build is
 * therefore rejected automatically instead of silently unlocking Detroit.
 *
 * iOS may refuse active Metal command buffers when an app leaves the foreground.
 * Madeira writes a fixed invalidation marker if this diagnostic becomes inactive
 * while its Wine process is running. This controller clears that marker before
 * the test starts and refuses to publish PASS proof if it appears during the run.
 */

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h>

#define GATE_SCHEMA "MADEIRA_DETROIT_DEVICE_GATE_V1"
#define PROOF_SCHEMA "MADEIRA_DETROIT_DEVICE_GATE_PROOF_V2"
#define PROOF_PATH "C:\\madeira-detroit-vulkan-gate.txt"
#define PROOF_TEMP_PATH "C:\\madeira-detroit-vulkan-gate.tmp"
#define FOREGROUND_INVALID_PATH "C:\\madeira-detroit-vulkan-gate-invalid.txt"
#define FNV64_OFFSET UINT64_C(14695981039346656037)
#define FNV64_PRIME UINT64_C(1099511628211)

typedef struct gate_stage {
    const char *name;
    const char *exe;
    DWORD timeout_ms;
} gate_stage;

static const char *const payload_names[] = {
    "vulkan_probe.exe",
    "vulkan_wsi_probe.exe",
    "vulkan_swapchain_probe.exe",
    "vulkan-device-gate-x64.exe",
};

static uint64_t fnv64_bytes(uint64_t hash, const unsigned char *data, size_t size)
{
    size_t i;
    for (i = 0; i < size; ++i) {
        hash ^= (uint64_t)data[i];
        hash *= FNV64_PRIME;
    }
    return hash;
}

static int payload_fingerprint(uint64_t *out_hash)
{
    unsigned char buffer[64 * 1024];
    uint64_t hash = FNV64_OFFSET;
    size_t i;

    for (i = 0; i < sizeof(payload_names) / sizeof(payload_names[0]); ++i) {
        char path[MAX_PATH];
        HANDLE file;
        DWORD got;
        const unsigned char separator = 0xffu;

        hash = fnv64_bytes(hash, (const unsigned char *)payload_names[i], strlen(payload_names[i]));
        hash = fnv64_bytes(hash, &separator, 1u);
        snprintf(path, sizeof(path), "C:\\windows\\system32\\%s", payload_names[i]);
        file = CreateFileA(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING,
                           FILE_ATTRIBUTE_NORMAL | FILE_FLAG_SEQUENTIAL_SCAN, NULL);
        if (file == INVALID_HANDLE_VALUE) {
            printf("PAYLOAD_HASH_RESULT=FAIL\n");
            printf("PAYLOAD_HASH_ERROR=CreateFileA:%s:%lu\n", payload_names[i], (unsigned long)GetLastError());
            return 10;
        }

        for (;;) {
            if (!ReadFile(file, buffer, (DWORD)sizeof(buffer), &got, NULL)) {
                DWORD err = GetLastError();
                CloseHandle(file);
                printf("PAYLOAD_HASH_RESULT=FAIL\n");
                printf("PAYLOAD_HASH_ERROR=ReadFile:%s:%lu\n", payload_names[i], (unsigned long)err);
                return 11;
            }
            if (!got) break;
            hash = fnv64_bytes(hash, buffer, (size_t)got);
        }
        CloseHandle(file);
    }

    *out_hash = hash;
    printf("PAYLOAD_FNV64=%016llx\n", (unsigned long long)hash);
    printf("PAYLOAD_HASH_RESULT=PASS\n");
    fflush(stdout);
    return 0;
}

static void clear_stale_proof(void)
{
    /* Stale PASS/invalidation state is more dangerous than no proof. */
    DeleteFileA(PROOF_TEMP_PATH);
    DeleteFileA(PROOF_PATH);
    DeleteFileA(FOREGROUND_INVALID_PATH);
}

static int foreground_integrity_ok(void)
{
    DWORD attrs = GetFileAttributesA(FOREGROUND_INVALID_PATH);
    if (attrs != INVALID_FILE_ATTRIBUTES) {
        printf("FOREGROUND_INTEGRITY=FAIL\n");
        printf("FOREGROUND_INVALIDATION=%s\n", FOREGROUND_INVALID_PATH);
        return 0;
    }
    if (GetLastError() != ERROR_FILE_NOT_FOUND && GetLastError() != ERROR_PATH_NOT_FOUND) {
        printf("FOREGROUND_INTEGRITY=FAIL\n");
        printf("FOREGROUND_ERROR=GetFileAttributesA:%lu\n", (unsigned long)GetLastError());
        return 0;
    }
    printf("FOREGROUND_INTEGRITY=PASS\n");
    return 1;
}

static int write_full_pass_proof(uint64_t payload_hash)
{
    char proof[1024];
    int proof_len;
    HANDLE file;
    DWORD written = 0;
    BOOL ok;

    proof_len = snprintf(
        proof, sizeof(proof),
        "SCHEMA=%s\r\n"
        "ARCH=x86_64-windows\r\n"
        "EXECUTION=physical-device-local\r\n"
        "FOREGROUND_INTEGRITY=PASS\r\n"
        "PAYLOAD_FNV64=%016llx\r\n"
        "VULKAN_DEVICE=PASS\r\n"
        "WIN32_SURFACE=PASS\r\n"
        "PRESENTED_120_FRAMES=PASS\r\n"
        "OVERALL=PASS\r\n"
        "NEXT_GATE=detroit-process-and-shader-compilation\r\n",
        PROOF_SCHEMA, (unsigned long long)payload_hash);
    if (proof_len <= 0 || (size_t)proof_len >= sizeof(proof)) {
        printf("PROOF_RESULT=FAIL\n");
        printf("PROOF_ERROR=format-overflow\n");
        return 29;
    }

    DeleteFileA(PROOF_TEMP_PATH);
    file = CreateFileA(PROOF_TEMP_PATH, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS,
                       FILE_ATTRIBUTE_NORMAL | FILE_FLAG_WRITE_THROUGH, NULL);
    if (file == INVALID_HANDLE_VALUE) {
        printf("PROOF_RESULT=FAIL\n");
        printf("PROOF_ERROR=CreateFileA:%lu\n", (unsigned long)GetLastError());
        return 30;
    }

    ok = WriteFile(file, proof, (DWORD)proof_len, &written, NULL);
    if (!ok || written != (DWORD)proof_len) {
        DWORD err = GetLastError();
        CloseHandle(file);
        DeleteFileA(PROOF_TEMP_PATH);
        printf("PROOF_RESULT=FAIL\n");
        printf("PROOF_ERROR=WriteFile:%lu:%lu/%lu\n",
               (unsigned long)err,
               (unsigned long)written,
               (unsigned long)proof_len);
        return 31;
    }

    if (!FlushFileBuffers(file)) {
        DWORD err = GetLastError();
        CloseHandle(file);
        DeleteFileA(PROOF_TEMP_PATH);
        printf("PROOF_RESULT=FAIL\n");
        printf("PROOF_ERROR=FlushFileBuffers:%lu\n", (unsigned long)err);
        return 32;
    }
    CloseHandle(file);

    if (!MoveFileExA(PROOF_TEMP_PATH, PROOF_PATH,
                     MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)) {
        DWORD err = GetLastError();
        DeleteFileA(PROOF_TEMP_PATH);
        printf("PROOF_RESULT=FAIL\n");
        printf("PROOF_ERROR=MoveFileExA:%lu\n", (unsigned long)err);
        return 33;
    }

    printf("PROOF_PATH=%s\n", PROOF_PATH);
    printf("PROOF_SCHEMA=%s\n", PROOF_SCHEMA);
    printf("PROOF_PAYLOAD_FNV64=%016llx\n", (unsigned long long)payload_hash);
    printf("PROOF_RESULT=PASS\n");
    fflush(stdout);
    return 0;
}

static int run_stage(const gate_stage *stage)
{
    STARTUPINFOA si;
    PROCESS_INFORMATION pi;
    char command[512];
    DWORD wait_result;
    DWORD exit_code = 0xffffffffu;
    BOOL ok;

    memset(&si, 0, sizeof(si));
    memset(&pi, 0, sizeof(pi));
    si.cb = sizeof(si);
    snprintf(command, sizeof(command), "\"C:\\windows\\system32\\%s\"", stage->exe);

    printf("GATE_BEGIN=%s\n", stage->name);
    printf("GATE_EXE=%s\n", stage->exe);
    fflush(stdout);

    ok = CreateProcessA(NULL, command, NULL, NULL, TRUE, 0, NULL, NULL, &si, &pi);
    if (!ok) {
        printf("GATE_RESULT=%s:FAIL\n", stage->name);
        printf("GATE_ERROR=CreateProcessA:%lu\n", (unsigned long)GetLastError());
        return 20;
    }

    wait_result = WaitForSingleObject(pi.hProcess, stage->timeout_ms);
    if (wait_result == WAIT_TIMEOUT) {
        TerminateProcess(pi.hProcess, 0xdead0001u);
        WaitForSingleObject(pi.hProcess, 5000);
        printf("GATE_RESULT=%s:FAIL\n", stage->name);
        printf("GATE_ERROR=TIMEOUT_MS:%lu\n", (unsigned long)stage->timeout_ms);
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
        return 21;
    }
    if (wait_result != WAIT_OBJECT_0) {
        printf("GATE_RESULT=%s:FAIL\n", stage->name);
        printf("GATE_ERROR=WAIT_FAILED:%lu\n", (unsigned long)GetLastError());
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
        return 22;
    }

    if (!GetExitCodeProcess(pi.hProcess, &exit_code)) {
        printf("GATE_RESULT=%s:FAIL\n", stage->name);
        printf("GATE_ERROR=GetExitCodeProcess:%lu\n", (unsigned long)GetLastError());
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
        return 23;
    }

    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);

    printf("GATE_CHILD_EXIT=%s:0x%08lx\n", stage->name, (unsigned long)exit_code);
    if (exit_code != 0) {
        printf("GATE_RESULT=%s:FAIL\n", stage->name);
        return 24;
    }

    printf("GATE_RESULT=%s:PASS\n", stage->name);
    fflush(stdout);
    return 0;
}

int main(void)
{
    static const gate_stage stages[] = {
        { "vulkan-device",  "vulkan_probe.exe",           60000 },
        { "win32-surface",  "vulkan_wsi_probe.exe",       60000 },
        { "present-120",    "vulkan_swapchain_probe.exe", 180000 },
    };
    uint64_t payload_hash = 0;
    size_t i;

    clear_stale_proof();

    printf("SCHEMA=%s\n", GATE_SCHEMA);
    printf("ARCH=x86_64-windows\n");
    printf("PURPOSE=prove-local-FEX-Wine-Vulkan-MoltenVK-Metal-path-before-Detroit\n");
    printf("STALE_PROOF_CLEARED=1\n");
    printf("FOREGROUND_GUARD_ARMED=1\n");
    fflush(stdout);

    if (payload_fingerprint(&payload_hash) != 0) {
        printf("OVERALL=FAIL\n");
        printf("FAILED_GATE=payload-fingerprint\n");
        printf("PROOF_RESULT=NOT_WRITTEN\n");
        printf("NEXT_ACTION=repair-device-gate-payload-before-launching-Detroit\n");
        fflush(stdout);
        return 12;
    }

    for (i = 0; i < sizeof(stages) / sizeof(stages[0]); ++i) {
        int rc = run_stage(&stages[i]);
        if (rc != 0) {
            size_t j;
            printf("OVERALL=FAIL\n");
            printf("FAILED_GATE=%s\n", stages[i].name);
            for (j = i + 1; j < sizeof(stages) / sizeof(stages[0]); ++j)
                printf("GATE_RESULT=%s:SKIP\n", stages[j].name);
            printf("PROOF_RESULT=NOT_WRITTEN\n");
            printf("NEXT_ACTION=fix-this-gate-before-launching-Detroit\n");
            fflush(stdout);
            return rc;
        }
    }

    printf("VULKAN_DEVICE=PASS\n");
    printf("WIN32_SURFACE=PASS\n");
    printf("PRESENTED_120_FRAMES=PASS\n");
    fflush(stdout);

    if (!foreground_integrity_ok()) {
        printf("OVERALL=FAIL\n");
        printf("FAILED_GATE=foreground-integrity\n");
        printf("PROOF_RESULT=NOT_WRITTEN\n");
        printf("NEXT_ACTION=rerun-graphics-test-with-Madeira-kept-in-foreground\n");
        fflush(stdout);
        return 28;
    }

    {
        int proof_rc = write_full_pass_proof(payload_hash);
        if (proof_rc != 0) {
            printf("OVERALL=FAIL\n");
            printf("FAILED_GATE=proof-publication\n");
            printf("NEXT_ACTION=fix-proof-publication-before-launching-Detroit\n");
            fflush(stdout);
            return proof_rc;
        }
    }

    printf("OVERALL=PASS\n");
    printf("NEXT_GATE=detroit-process-and-shader-compilation\n");
    fflush(stdout);
    return 0;
}

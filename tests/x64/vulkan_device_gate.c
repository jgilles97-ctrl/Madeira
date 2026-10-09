/*
 * vulkan_device_gate.c - one-command Detroit Vulkan device gate for Madeira.
 *
 * This x86-64 Windows program runs the three existing Vulkan canaries through
 * the same Wine/FEX child-process path used by real Windows software on iOS.
 * It stops at the first failed or hung stage and prints a small, stable summary
 * that can be copied directly from madeira-log.txt.
 */

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <string.h>

#define GATE_SCHEMA "MADEIRA_DETROIT_DEVICE_GATE_V1"

typedef struct gate_stage {
    const char *name;
    const char *exe;
    DWORD timeout_ms;
} gate_stage;

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

    /* bInheritHandles=TRUE keeps Madeira's stdout/stderr routing attached, so
     * every child canary writes its detailed evidence into madeira-log.txt. */
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
    size_t i;

    printf("SCHEMA=%s\n", GATE_SCHEMA);
    printf("ARCH=x86_64-windows\n");
    printf("PURPOSE=prove-local-FEX-Wine-Vulkan-MoltenVK-Metal-path-before-Detroit\n");
    fflush(stdout);

    for (i = 0; i < sizeof(stages) / sizeof(stages[0]); ++i) {
        int rc = run_stage(&stages[i]);
        if (rc != 0) {
            size_t j;
            printf("OVERALL=FAIL\n");
            printf("FAILED_GATE=%s\n", stages[i].name);
            for (j = i + 1; j < sizeof(stages) / sizeof(stages[0]); ++j)
                printf("GATE_RESULT=%s:SKIP\n", stages[j].name);
            printf("NEXT_ACTION=fix-this-gate-before-launching-Detroit\n");
            fflush(stdout);
            return rc;
        }
    }

    printf("VULKAN_DEVICE=PASS\n");
    printf("WIN32_SURFACE=PASS\n");
    printf("PRESENTED_120_FRAMES=PASS\n");
    printf("OVERALL=PASS\n");
    printf("NEXT_GATE=detroit-process-and-shader-compilation\n");
    fflush(stdout);
    return 0;
}

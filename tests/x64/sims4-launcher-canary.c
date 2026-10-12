#define COBJMACROS
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <winsock2.h>
#include <ws2tcpip.h>
#include <winhttp.h>
#include <objbase.h>
#include <netlistmgr.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/*
 * Pre-EA-App canary for the Sims 4 iPad lane.
 *
 * It deliberately tests small Windows capabilities that launchers commonly
 * depend on before we spend a device run inside a large CEF launcher:
 *   - x64/FEX process execution
 *   - child process creation + lifetime
 *   - Service Control Manager reachability
 *   - EABackgroundService registration/query + exact state
 *   - sensapi!IsNetworkAlive
 *   - Network List Manager COM (netprofm.dll)
 *   - Winsock TCP
 *   - WinHTTP HTTPS
 *
 * It does NOT call InternetCheckConnectionW: Madeira issue #189 reports that
 * call can trigger an unrecoverable host fault on the affected baseline.
 */

static int failures = 0;

static void result(const char *name, int ok, const char *detail)
{
    printf("CANARY %-24s %s %s\n", name, ok ? "PASS" : "FAIL", detail ? detail : "");
    fflush(stdout);
    if (!ok) failures++;
}

/* Observation-only line: records state without deciding that the state itself is fatal. */
static void observe(const char *name, const char *detail)
{
    printf("CANARY %-24s OBSERVE %s\n", name, detail ? detail : "");
    fflush(stdout);
}

static const char *service_state_name(DWORD state)
{
    switch (state) {
        case SERVICE_STOPPED: return "STOPPED";
        case SERVICE_START_PENDING: return "START_PENDING";
        case SERVICE_STOP_PENDING: return "STOP_PENDING";
        case SERVICE_RUNNING: return "RUNNING";
        case SERVICE_CONTINUE_PENDING: return "CONTINUE_PENDING";
        case SERVICE_PAUSE_PENDING: return "PAUSE_PENDING";
        case SERVICE_PAUSED: return "PAUSED";
        default: return "UNKNOWN";
    }
}

static int child_mode(void)
{
    Sleep(250);
    return 42;
}

static void test_child_process(const char *self)
{
    char cmd[4096];
    STARTUPINFOA si;
    PROCESS_INFORMATION pi;
    DWORD exit_code = 0;
    memset(&si, 0, sizeof(si));
    memset(&pi, 0, sizeof(pi));
    si.cb = sizeof(si);
    snprintf(cmd, sizeof(cmd), "\"%s\" --child", self);

    if (!CreateProcessA(NULL, cmd, NULL, NULL, FALSE, 0, NULL, NULL, &si, &pi)) {
        char detail[128];
        snprintf(detail, sizeof(detail), "CreateProcess error=%lu", (unsigned long)GetLastError());
        result("child-process", 0, detail);
        return;
    }
    WaitForSingleObject(pi.hProcess, 5000);
    if (!GetExitCodeProcess(pi.hProcess, &exit_code)) exit_code = 0xffffffffu;
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);

    {
        char detail[128];
        snprintf(detail, sizeof(detail), "exit=%lu expected=42", (unsigned long)exit_code);
        result("child-process", exit_code == 42, detail);
    }
}

typedef BOOL (WINAPI *IsNetworkAliveFn)(LPDWORD);

static void test_sensapi(void)
{
    HMODULE mod = LoadLibraryA("sensapi.dll");
    if (!mod) {
        char detail[128];
        snprintf(detail, sizeof(detail), "LoadLibrary error=%lu", (unsigned long)GetLastError());
        result("sensapi", 0, detail);
        return;
    }
    IsNetworkAliveFn fn = (IsNetworkAliveFn)GetProcAddress(mod, "IsNetworkAlive");
    if (!fn) {
        result("sensapi", 0, "IsNetworkAlive export missing");
        FreeLibrary(mod);
        return;
    }
    {
        DWORD flags = 0;
        BOOL ok = fn(&flags);
        char detail[128];
        snprintf(detail, sizeof(detail), "alive=%d flags=0x%lx", ok ? 1 : 0, (unsigned long)flags);
        result("sensapi", ok ? 1 : 0, detail);
    }
    FreeLibrary(mod);
}

static void test_network_list_manager(void)
{
    INetworkListManager *nlm = NULL;
    VARIANT_BOOL connected = VARIANT_FALSE;
    NLM_CONNECTIVITY connectivity = NLM_CONNECTIVITY_DISCONNECTED;
    HRESULT init = CoInitializeEx(NULL, COINIT_APARTMENTTHREADED);
    HRESULT hr = CoCreateInstance(&CLSID_NetworkListManager, NULL, CLSCTX_INPROC_SERVER,
                                  &IID_INetworkListManager, (void **)&nlm);
    if (FAILED(hr) || !nlm) {
        char detail[160];
        snprintf(detail, sizeof(detail), "CoCreateInstance hr=0x%08lx", (unsigned long)hr);
        result("network-list-manager", 0, detail);
        if (SUCCEEDED(init)) CoUninitialize();
        return;
    }

    hr = INetworkListManager_get_IsConnectedToInternet(nlm, &connected);
    if (SUCCEEDED(hr))
        hr = INetworkListManager_GetConnectivity(nlm, &connectivity);
    {
        char detail[192];
        snprintf(detail, sizeof(detail), "hr=0x%08lx internet=%d connectivity=0x%x",
                 (unsigned long)hr, connected == VARIANT_TRUE ? 1 : 0, (unsigned int)connectivity);
        result("network-list-manager", SUCCEEDED(hr) && connected == VARIANT_TRUE, detail);
    }
    INetworkListManager_Release(nlm);
    if (SUCCEEDED(init)) CoUninitialize();
}

static void test_tcp(void)
{
    WSADATA wsa;
    SOCKET s = INVALID_SOCKET;
    struct sockaddr_in addr;
    int ok = 0;
    char detail[128] = {0};

    if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0) {
        result("tcp-1.1.1.1-443", 0, "WSAStartup failed");
        return;
    }
    s = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (s == INVALID_SOCKET) {
        snprintf(detail, sizeof(detail), "socket error=%d", WSAGetLastError());
        result("tcp-1.1.1.1-443", 0, detail);
        WSACleanup();
        return;
    }
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons(443);
    inet_pton(AF_INET, "1.1.1.1", &addr.sin_addr);
    ok = connect(s, (struct sockaddr *)&addr, sizeof(addr)) == 0;
    snprintf(detail, sizeof(detail), "connect=%s wsa=%d", ok ? "ok" : "failed", ok ? 0 : WSAGetLastError());
    result("tcp-1.1.1.1-443", ok, detail);
    closesocket(s);
    WSACleanup();
}

static void test_winhttp(void)
{
    HINTERNET session = NULL, connection = NULL, request = NULL;
    DWORD status = 0, size = sizeof(status);
    int ok = 0;
    char detail[160] = {0};

    session = WinHttpOpen(L"Madeira-Sims4-Canary/1.0", WINHTTP_ACCESS_TYPE_AUTOMATIC_PROXY,
                          WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0);
    if (!session) goto done;
    connection = WinHttpConnect(session, L"example.com", INTERNET_DEFAULT_HTTPS_PORT, 0);
    if (!connection) goto done;
    request = WinHttpOpenRequest(connection, L"HEAD", L"/", NULL, WINHTTP_NO_REFERER,
                                 WINHTTP_DEFAULT_ACCEPT_TYPES, WINHTTP_FLAG_SECURE);
    if (!request) goto done;
    if (!WinHttpSendRequest(request, WINHTTP_NO_ADDITIONAL_HEADERS, 0,
                            WINHTTP_NO_REQUEST_DATA, 0, 0, 0)) goto done;
    if (!WinHttpReceiveResponse(request, NULL)) goto done;
    if (!WinHttpQueryHeaders(request, WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER,
                             WINHTTP_HEADER_NAME_BY_INDEX, &status, &size, WINHTTP_NO_HEADER_INDEX)) goto done;
    ok = status >= 200 && status < 500;

done:
    snprintf(detail, sizeof(detail), "http=%lu error=%lu", (unsigned long)status,
             ok ? 0ul : (unsigned long)GetLastError());
    result("winhttp-https", ok, detail);
    if (request) WinHttpCloseHandle(request);
    if (connection) WinHttpCloseHandle(connection);
    if (session) WinHttpCloseHandle(session);
}

static void test_services(void)
{
    SC_HANDLE scm = OpenSCManagerW(NULL, NULL, SC_MANAGER_CONNECT);
    SC_HANDLE svc = NULL;
    SERVICE_STATUS_PROCESS status;
    DWORD needed = 0;
    char detail[256];

    if (!scm) {
        snprintf(detail, sizeof(detail), "OpenSCManager error=%lu", (unsigned long)GetLastError());
        result("service-control-manager", 0, detail);
        return;
    }
    result("service-control-manager", 1, "open");

    svc = OpenServiceW(scm, L"EABackgroundService", SERVICE_QUERY_STATUS);
    if (!svc) {
        snprintf(detail, sizeof(detail), "OpenService error=%lu", (unsigned long)GetLastError());
        result("ea-background-service", 0, detail);
        CloseServiceHandle(scm);
        return;
    }

    memset(&status, 0, sizeof(status));
    if (!QueryServiceStatusEx(svc, SC_STATUS_PROCESS_INFO, (LPBYTE)&status,
                              (DWORD)sizeof(status), &needed)) {
        snprintf(detail, sizeof(detail), "QueryServiceStatusEx error=%lu needed=%lu",
                 (unsigned long)GetLastError(), (unsigned long)needed);
        result("ea-background-service", 0, detail);
    } else {
        snprintf(detail, sizeof(detail),
                 "query=ok state=%lu state_name=%s pid=%lu exit=%lu service_exit=%lu",
                 (unsigned long)status.dwCurrentState,
                 service_state_name(status.dwCurrentState),
                 (unsigned long)status.dwProcessId,
                 (unsigned long)status.dwWin32ExitCode,
                 (unsigned long)status.dwServiceSpecificExitCode);
        result("ea-background-service", 1, detail);
        if (status.dwCurrentState == SERVICE_STOPPED || status.dwCurrentState == SERVICE_STOP_PENDING)
            observe("ea-service-stale-check", detail);
    }

    CloseServiceHandle(svc);
    CloseServiceHandle(scm);
}

int main(int argc, char **argv)
{
    char self[MAX_PATH];
    DWORD n;
    if (argc > 1 && strcmp(argv[1], "--child") == 0) return child_mode();

    n = GetModuleFileNameA(NULL, self, (DWORD)sizeof(self));
    result("x64-process", n > 0 && n < sizeof(self), n ? self : "GetModuleFileName failed");
    if (n > 0 && n < sizeof(self)) test_child_process(self);
    else failures++;

    test_services();
    test_sensapi();
    test_network_list_manager();
    test_tcp();
    test_winhttp();

    printf("CANARY SUMMARY failures=%d\n", failures);
    fflush(stdout);
    return failures ? 10 + failures : 0;
}

/* Compile-only canary for the public iOS memory APIs used by Detroit tests.
 * This is built against the real iPhoneOS SDK in CI; it is never shipped. */

#include <stdint.h>
#include <os/proc.h>
#include <sys/resource.h>
#include <unistd.h>

/* Match Apple's iOS sample: <sys/resource.h> provides the types/constants,
 * while the function is explicitly declared for stable compilation. */
extern int proc_pid_rusage(int pid, int flavor, rusage_info_t *buffer);

uint64_t detroit_probe_available_memory(void)
{
    return (uint64_t)os_proc_available_memory();
}

int detroit_probe_footprint(uint64_t *current, uint64_t *peak)
{
    rusage_info_current info;
    int ret = proc_pid_rusage(getpid(), RUSAGE_INFO_CURRENT, (rusage_info_t)&info);
    if (ret) return ret;
    if (current) *current = info.ri_phys_footprint;
    if (peak) *peak = info.ri_lifetime_max_phys_footprint;
    return 0;
}

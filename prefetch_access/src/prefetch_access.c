/*
 * 2d Access-pattern prefetch (interior-only) / 2e (interior + leaf).
 *
 * Inputs:
 *   db          : sqlite file (memory-mapped read-only)
 *   classify    : page_number,page_type,file_offset (one row per page)
 *   hotpages    : page_number,is_resident             (post-warmup mincore dump)
 *   n_interior  : max interior pages to prefetch (or 0 to take all resident interior)
 *   n_leaf      : max leaf pages to prefetch     (0 = 2d mode; >0 = 2e mode)
 *   page_size   : 4096
 *
 * Selection rule:
 *   - Intersect (page_type startsWith "interior") with (is_resident == 1)  → 2d set
 *   - Intersect (page_type startsWith "leaf")     with (is_resident == 1)  → 2e leaf set
 *   - Take up to n_interior / n_leaf, sorted by file_offset (deterministic, low madvise cost)
 *   - Emit one madvise(WILLNEED) per page; time the syscalls.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#define MAX_PAGES 65536

static long long now_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (long long)ts.tv_sec * 1000000000LL + ts.tv_nsec;
}

static int cmp_ll(const void *a, const void *b) {
    long long x = *(long long *)a, y = *(long long *)b;
    return (x > y) - (x < y);
}

struct page_info {
    int is_interior;  /* 1 = interior, 2 = leaf, 0 = other */
    long long offset;
};

int main(int argc, char *argv[]) {
    if (argc != 7) {
        fprintf(stderr,
            "Usage: %s <db> <classify.csv> <hotpages.csv> <n_interior> <n_leaf> <page_size>\n"
            "  n_interior : cap on interior pages to prefetch (0 = no cap, take all)\n"
            "  n_leaf     : cap on leaf pages to prefetch     (0 = 2d mode, skip leaves)\n",
            argv[0]);
        return 1;
    }
    const char *db_path     = argv[1];
    const char *classify    = argv[2];
    const char *hot         = argv[3];
    int cap_interior        = atoi(argv[4]);
    int cap_leaf            = atoi(argv[5]);
    int page_size           = atoi(argv[6]);

    /* mmap the db so madvise has a real VMA target */
    int fd = open(db_path, O_RDONLY);
    if (fd < 0) { perror("open db"); return 1; }
    struct stat st; fstat(fd, &st);
    size_t db_size = st.st_size;
    void *map = mmap(NULL, db_size, PROT_READ, MAP_SHARED, fd, 0);
    if (map == MAP_FAILED) { perror("mmap"); return 1; }

    /* Load classify: page_number -> (is_interior, file_offset) */
    static struct page_info pinfo[MAX_PAGES];
    FILE *f = fopen(classify, "r");
    if (!f) { perror("fopen classify"); return 1; }
    char line[512];
    int header = 1;
    while (fgets(line, sizeof(line), f)) {
        if (header) { header = 0; continue; }
        int pn; char ptype[64]; long long off;
        if (sscanf(line, "%d,%63[^,],%lld", &pn, ptype, &off) != 3) continue;
        if (pn < 0 || pn >= MAX_PAGES) continue;
        pinfo[pn].offset = off;
        if (strncmp(ptype, "interior", 8) == 0)      pinfo[pn].is_interior = 1;
        else if (strncmp(ptype, "leaf", 4) == 0)     pinfo[pn].is_interior = 2;
        else                                          pinfo[pn].is_interior = 0;
    }
    fclose(f);

    /* Load hotpages, build resident interior + leaf offset lists */
    long long off_interior[MAX_PAGES];
    long long off_leaf[MAX_PAGES];
    int n_int_resident = 0, n_leaf_resident = 0;

    f = fopen(hot, "r");
    if (!f) { perror("fopen hotpages"); return 1; }
    header = 1;
    while (fgets(line, sizeof(line), f)) {
        if (header) { header = 0; continue; }
        int pn, res;
        if (sscanf(line, "%d,%d", &pn, &res) != 2) continue;
        if (pn < 0 || pn >= MAX_PAGES) continue;
        if (!res) continue;
        if (pinfo[pn].is_interior == 1 && n_int_resident < MAX_PAGES)
            off_interior[n_int_resident++] = pinfo[pn].offset;
        else if (pinfo[pn].is_interior == 2 && n_leaf_resident < MAX_PAGES)
            off_leaf[n_leaf_resident++] = pinfo[pn].offset;
    }
    fclose(f);

    /* Sort by file offset (cheap; OS readahead may coalesce neighbors) */
    qsort(off_interior, n_int_resident, sizeof(long long), cmp_ll);
    qsort(off_leaf, n_leaf_resident, sizeof(long long), cmp_ll);

    int n_int_pick  = (cap_interior == 0 || cap_interior > n_int_resident)  ? n_int_resident  : cap_interior;
    int n_leaf_pick = (cap_leaf > n_leaf_resident) ? n_leaf_resident : cap_leaf;
    /* cap_leaf == 0 → n_leaf_pick = 0 (2d mode, skip leaves). Caller passes K explicitly for 2e. */

    long long t0 = now_ns();
    for (int i = 0; i < n_int_pick; i++)
        madvise((char *)map + off_interior[i], page_size, MADV_WILLNEED);
    for (int i = 0; i < n_leaf_pick; i++)
        madvise((char *)map + off_leaf[i], page_size, MADV_WILLNEED);
    long long t1 = now_ns();

    int total_syscalls = n_int_pick + n_leaf_pick;
    printf("n_interior=%d n_leaf=%d syscalls=%d resident_interior_total=%d resident_leaf_total=%d time_us=%.2f\n",
           n_int_pick, n_leaf_pick, total_syscalls,
           n_int_resident, n_leaf_resident,
           (t1 - t0) / 1000.0);

    munmap(map, db_size);
    close(fd);
    return 0;
}

#ifndef HOROS_DICOM_GLOBAL_ABORT_H
#define HOROS_DICOM_GLOBAL_ABORT_H
/* C-compatible: shared by the app and the vendored Objective-C++ DICOM SCP.
 * No environment override: inherited TMPDIR can name a shared directory.
 */
#include <unistd.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <limits.h>
#include <errno.h>
#include <time.h>

static inline int HorosDICOMAbortPrivateDirectory(int fd) {
    struct stat st;
    return fd >= 0 && fstat(fd, &st) == 0 && S_ISDIR(st.st_mode) &&
        st.st_uid == geteuid() && (st.st_mode & 077) == 0;
}
static inline int HorosDICOMAbortOpenDirectory(void) {
    char root[PATH_MAX];
    size_t size = confstr(_CS_DARWIN_USER_TEMP_DIR, root, sizeof(root));
    if (!size || size > sizeof(root)) return -1;
    int parent = open(root, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (!HorosDICOMAbortPrivateDirectory(parent)) { if (parent >= 0) close(parent); return -1; }
    if (mkdirat(parent, "horos-dicom-control", 0700) != 0 && errno != EEXIST) { close(parent); return -1; }
    int directory = openat(parent, "horos-dicom-control", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    close(parent);
    if (!HorosDICOMAbortPrivateDirectory(directory)) { if (directory >= 0) close(directory); return -1; }
    return directory;
}
static inline int HorosDICOMAbortValidFile(int directory, struct stat *st) {
    return HorosDICOMAbortPrivateDirectory(directory) &&
        fstatat(directory, "abort", st, AT_SYMLINK_NOFOLLOW) == 0 &&
        S_ISREG(st->st_mode) && st->st_uid == geteuid() && (st->st_mode & 077) == 0;
}
static inline int HorosDICOMAbortRequestedInDirectory(int directory) {
    struct stat st;
    if (!HorosDICOMAbortValidFile(directory, &st)) return 0;
    time_t now = time(NULL);
    /* A crashed caller cannot leave every future retrieval disabled. */
    return now >= st.st_mtime && now - st.st_mtime <= 10;
}
static inline int HorosDICOMAbortBeginInDirectory(int directory) {
    if (!HorosDICOMAbortPrivateDirectory(directory)) return 0;
    int fd = openat(directory, "abort", O_WRONLY | O_CREAT | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC, 0600);
    if (fd < 0) return 0;
    struct stat st;
    int valid = fstat(fd, &st) == 0 && S_ISREG(st.st_mode) && st.st_uid == geteuid() && (st.st_mode & 077) == 0;
    int result = valid && futimens(fd, NULL) == 0;
    close(fd);
    return result;
}
static inline void HorosDICOMAbortEndInDirectory(int directory) {
    struct stat st;
    if (HorosDICOMAbortValidFile(directory, &st)) unlinkat(directory, "abort", 0);
}
static inline int HorosDICOMGlobalAbortRequested(void) {
    int directory = HorosDICOMAbortOpenDirectory();
    if (directory < 0) return 0;
    int result = HorosDICOMAbortRequestedInDirectory(directory);close(directory);return result;
}
static inline int HorosDICOMGlobalAbortBegin(void) {
    int directory = HorosDICOMAbortOpenDirectory();
    if (directory < 0) return 0;
    int result = HorosDICOMAbortBeginInDirectory(directory);close(directory);return result;
}
static inline void HorosDICOMGlobalAbortEnd(void) {
    int directory = HorosDICOMAbortOpenDirectory();
    if (directory >= 0) { HorosDICOMAbortEndInDirectory(directory);close(directory); }
}
#endif

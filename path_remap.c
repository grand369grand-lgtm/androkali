/*
 * libpath_remap.so - LD_PRELOAD library for anroot (Termux fork)
 *
 * Translates filesystem paths from com.termux to com.anroot at runtime.
 * This allows official Termux .deb packages to work under the com.anroot
 * applicationId without modification.
 *
 * Both "com.termux" and "com.anroot" are exactly 10 characters long,
 * enabling efficient in-place string replacement without buffer resizing.
 *
 * Build for all architectures:
 *   aarch64: <ndk-clang> -shared -fPIC -o libpath_remap.so path_remap.c -ldl
 *   arm:      <ndk-clang> -shared -fPIC -o libpath_remap.so path_remap.c -ldl
 *   x86_64:   <ndk-clang> -shared -fPIC -o libpath_remap.so path_remap.c -ldl
 *   x86:      <ndk-clang> -shared -fPIC -o libpath_remap.so path_remap.c -ldl
 */

#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <dirent.h>
#include <unistd.h>
#include <limits.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/statvfs.h>
#include <sys/xattr.h>

/* com.termux and com.anroot are both exactly 10 characters */
#define OLD_PKG     "com.termux"
#define NEW_PKG     "com.anroot"
#define PKG_NAME_LEN 10

/* Thread-local buffers for translated paths (2 for functions with 2 path args) */
static __thread char g_translated1[PATH_MAX];
static __thread char g_translated2[PATH_MAX];

/*
 * Translate a path by replacing all occurrences of "com.termux" with "com.anroot".
 * Since both strings are the same length (10 chars), this is a simple in-place
 * replacement that doesn't change the path length.
 *
 * Returns the original path if no translation is needed, or a thread-local
 * buffer with the translated path.
 */
static const char *translate_path(const char *path, char *buf, size_t bufsize)
{
    if (path == NULL) return NULL;

    /* Quick check - if path doesn't contain com.termux, no translation needed */
    if (strstr(path, OLD_PKG) == NULL) return path;

    /* Copy path to buffer and replace all occurrences */
    size_t len = strlen(path);
    if (len >= bufsize) len = bufsize - 1;
    memcpy(buf, path, len + 1);
    buf[len] = '\0';

    /* Replace all occurrences of com.termux with com.anroot */
    char *pos;
    while ((pos = strstr(buf, OLD_PKG)) != NULL) {
        memcpy(pos, NEW_PKG, PKG_NAME_LEN);
    }

    return buf;
}

/* Convenience macros for single-path and dual-path translations */
#define T1(path) translate_path(path, g_translated1, sizeof(g_translated1))
#define T2(path) translate_path(path, g_translated2, sizeof(g_translated2))

/* Macro to get the real function pointer via dlsym */
#define GET_REAL(name) \
    static __typeof__(name) *real_##name = NULL; \
    if (!real_##name) real_##name = dlsym(RTLD_NEXT, #name); \
    if (!real_##name) return -1;

#define GET_REAL_PTR(name) \
    static __typeof__(name) *real_##name = NULL; \
    if (!real_##name) real_##name = dlsym(RTLD_NEXT, #name); \
    if (!real_##name) return NULL;

/* ========================================================================
 * File access / stat family
 * ======================================================================== */

int stat(const char *pathname, struct stat *statbuf)
{
    GET_REAL(stat);
    return real_stat(T1(pathname), statbuf);
}

int stat64(const char *pathname, struct stat64 *statbuf)
{
    GET_REAL(stat64);
    return real_stat64(T1(pathname), statbuf);
}

int lstat(const char *pathname, struct stat *statbuf)
{
    GET_REAL(lstat);
    return real_lstat(T1(pathname), statbuf);
}

int lstat64(const char *pathname, struct stat64 *statbuf)
{
    GET_REAL(lstat64);
    return real_lstat64(T1(pathname), statbuf);
}

int fstatat(int dirfd, const char *pathname, struct stat *statbuf, int flags)
{
    GET_REAL(fstatat);
    return real_fstatat(dirfd, T1(pathname), statbuf, flags);
}

int fstatat64(int dirfd, const char *pathname, struct stat64 *statbuf, int flags)
{
    GET_REAL(fstatat64);
    return real_fstatat64(dirfd, T1(pathname), statbuf, flags);
}

int statx(int dirfd, const char *pathname, int flags, unsigned int mask, struct statx *statxbuf)
{
    GET_REAL(statx);
    return real_statx(dirfd, T1(pathname), flags, mask, statxbuf);
}

int access(const char *pathname, int mode)
{
    GET_REAL(access);
    return real_access(T1(pathname), mode);
}

int faccessat(int dirfd, const char *pathname, int mode, int flags)
{
    GET_REAL(faccessat);
    return real_faccessat(dirfd, T1(pathname), mode, flags);
}

/* ========================================================================
 * File open / create
 * ======================================================================== */

int open(const char *pathname, int flags, ...)
{
    mode_t mode = 0;
    if (flags & (O_CREAT | O_TMPFILE)) {
        va_list ap;
        va_start(ap, flags);
        mode = (mode_t)va_arg(ap, int);
        va_end(ap);
    }
    GET_REAL(open);
    return real_open(T1(pathname), flags, mode);
}

int open64(const char *pathname, int flags, ...)
{
    mode_t mode = 0;
    if (flags & (O_CREAT | O_TMPFILE)) {
        va_list ap;
        va_start(ap, flags);
        mode = (mode_t)va_arg(ap, int);
        va_end(ap);
    }
    GET_REAL(open64);
    return real_open64(T1(pathname), flags, mode);
}

int openat(int dirfd, const char *pathname, int flags, ...)
{
    mode_t mode = 0;
    if (flags & (O_CREAT | O_TMPFILE)) {
        va_list ap;
        va_start(ap, flags);
        mode = (mode_t)va_arg(ap, int);
        va_end(ap);
    }
    GET_REAL(openat);
    return real_openat(dirfd, T1(pathname), flags, mode);
}

int openat64(int dirfd, const char *pathname, int flags, ...)
{
    mode_t mode = 0;
    if (flags & (O_CREAT | O_TMPFILE)) {
        va_list ap;
        va_start(ap, flags);
        mode = (mode_t)va_arg(ap, int);
        va_end(ap);
    }
    GET_REAL(openat64);
    return real_openat64(dirfd, T1(pathname), flags, mode);
}

int creat(const char *pathname, mode_t mode)
{
    GET_REAL(creat);
    return real_creat(T1(pathname), mode);
}

int creat64(const char *pathname, mode_t mode)
{
    GET_REAL(creat64);
    return real_creat64(T1(pathname), mode);
}

/* ========================================================================
 * Directory operations
 * ======================================================================== */

int mkdir(const char *pathname, mode_t mode)
{
    GET_REAL(mkdir);
    return real_mkdir(T1(pathname), mode);
}

int mkdirat(int dirfd, const char *pathname, mode_t mode)
{
    GET_REAL(mkdirat);
    return real_mkdirat(dirfd, T1(pathname), mode);
}

int rmdir(const char *pathname)
{
    GET_REAL(rmdir);
    return real_rmdir(T1(pathname));
}

DIR *opendir(const char *name)
{
    GET_REAL_PTR(opendir);
    return real_opendir(T1(name));
}

int scandir(const char *dirp, struct dirent ***namelist,
            int (*filter)(const struct dirent *),
            int (*compar)(const struct dirent **, const struct dirent **))
{
    GET_REAL(scandir);
    return real_scandir(T1(dirp), namelist, filter, compar);
}

int scandirat(int dirfd, const char *dirp, struct dirent ***namelist,
              int (*filter)(const struct dirent *),
              int (*compar)(const struct dirent **, const struct dirent **))
{
    GET_REAL(scandirat);
    return real_scandirat(dirfd, T1(dirp), namelist, filter, compar);
}

/* ========================================================================
 * File metadata / permissions
 * ======================================================================== */

int chmod(const char *pathname, mode_t mode)
{
    GET_REAL(chmod);
    return real_chmod(T1(pathname), mode);
}

int fchmodat(int dirfd, const char *pathname, mode_t mode, int flags)
{
    GET_REAL(fchmodat);
    return real_fchmodat(dirfd, T1(pathname), mode, flags);
}

int chown(const char *pathname, uid_t owner, gid_t group)
{
    GET_REAL(chown);
    return real_chown(T1(pathname), owner, group);
}

int lchown(const char *pathname, uid_t owner, gid_t group)
{
    GET_REAL(lchown);
    return real_lchown(T1(pathname), owner, group);
}

int fchownat(int dirfd, const char *pathname, uid_t owner, gid_t group, int flags)
{
    GET_REAL(fchownat);
    return real_fchownat(dirfd, T1(pathname), owner, group, flags);
}

/* ========================================================================
 * Link / unlink / rename / symlink
 * ======================================================================== */

int link(const char *oldpath, const char *newpath)
{
    GET_REAL(link);
    return real_link(T1(oldpath), T2(newpath));
}

int linkat(int olddirfd, const char *oldpath, int newdirfd, const char *newpath, int flags)
{
    GET_REAL(linkat);
    return real_linkat(olddirfd, T1(oldpath), newdirfd, T2(newpath), flags);
}

int unlink(const char *pathname)
{
    GET_REAL(unlink);
    return real_unlink(T1(pathname));
}

int unlinkat(int dirfd, const char *pathname, int flags)
{
    GET_REAL(unlinkat);
    return real_unlinkat(dirfd, T1(pathname), flags);
}

int rename(const char *oldpath, const char *newpath)
{
    GET_REAL(rename);
    return real_rename(T1(oldpath), T2(newpath));
}

int renameat(int olddirfd, const char *oldpath, int newdirfd, const char *newpath)
{
    GET_REAL(renameat);
    return real_renameat(olddirfd, T1(oldpath), newdirfd, T2(newpath));
}

int renameat2(int olddirfd, const char *oldpath, int newdirfd, const char *newpath, unsigned int flags)
{
    GET_REAL(renameat2);
    return real_renameat2(olddirfd, T1(oldpath), newdirfd, T2(newpath), flags);
}

int symlink(const char *target, const char *linkpath)
{
    GET_REAL(symlink);
    return real_symlink(T1(target), T2(linkpath));
}

int symlinkat(const char *target, int newdirfd, const char *linkpath)
{
    GET_REAL(symlinkat);
    return real_symlinkat(T1(target), newdirfd, T2(linkpath));
}

ssize_t readlink(const char *pathname, char *buf, size_t bufsiz)
{
    GET_REAL(readlink);
    return real_readlink(T1(pathname), buf, bufsiz);
}

ssize_t readlinkat(int dirfd, const char *pathname, char *buf, size_t bufsiz)
{
    GET_REAL(readlinkat);
    return real_readlinkat(dirfd, T1(pathname), buf, bufsiz);
}

/* ========================================================================
 * File truncation
 * ======================================================================== */

int truncate(const char *pathname, off_t length)
{
    GET_REAL(truncate);
    return real_truncate(T1(pathname), length);
}

int truncate64(const char *pathname, off64_t length)
{
    GET_REAL(truncate64);
    return real_truncate64(T1(pathname), length);
}

/* ========================================================================
 * Extended attributes
 * ======================================================================== */

ssize_t getxattr(const char *pathname, const char *name, void *value, size_t size)
{
    GET_REAL(getxattr);
    return real_getxattr(T1(pathname), name, value, size);
}

ssize_t lgetxattr(const char *pathname, const char *name, void *value, size_t size)
{
    GET_REAL(lgetxattr);
    return real_lgetxattr(T1(pathname), name, value, size);
}

int setxattr(const char *pathname, const char *name, const void *value, size_t size, int flags)
{
    GET_REAL(setxattr);
    return real_setxattr(T1(pathname), name, value, size, flags);
}

int lsetxattr(const char *pathname, const char *name, const void *value, size_t size, int flags)
{
    GET_REAL(lsetxattr);
    return real_lsetxattr(T1(pathname), name, value, size, flags);
}

int removexattr(const char *pathname, const char *name)
{
    GET_REAL(removexattr);
    return real_removexattr(T1(pathname), name);
}

int lremovexattr(const char *pathname, const char *name)
{
    GET_REAL(lremovexattr);
    return real_lremovexattr(T1(pathname), name);
}

/* ========================================================================
 * Other filesystem operations
 * ======================================================================== */

int statvfs(const char *pathname, struct statvfs *buf)
{
    GET_REAL(statvfs);
    return real_statvfs(T1(pathname), buf);
}

int statvfs64(const char *pathname, struct statvfs64 *buf)
{
    GET_REAL(statvfs64);
    return real_statvfs64(T1(pathname), buf);
}

long pathconf(const char *pathname, int name)
{
    static __typeof__(pathconf) *real_fn = NULL;
    if (!real_fn) real_fn = dlsym(RTLD_NEXT, "pathconf");
    if (!real_fn) return -1;
    return real_fn(T1(pathname), name);
}

char *realpath(const char *pathname, char *resolved)
{
    GET_REAL_PTR(realpath);
    return real_realpath(T1(pathname), resolved);
}

int utimes(const char *pathname, const struct timeval times[2])
{
    GET_REAL(utimes);
    return real_utimes(T1(pathname), times);
}

int lutimes(const char *pathname, const struct timeval times[2])
{
    GET_REAL(lutimes);
    return real_lutimes(T1(pathname), times);
}

int mknod(const char *pathname, mode_t mode, dev_t dev)
{
    GET_REAL(mknod);
    return real_mknod(T1(pathname), mode, dev);
}

int mknodat(int dirfd, const char *pathname, mode_t mode, dev_t dev)
{
    GET_REAL(mknodat);
    return real_mknodat(dirfd, T1(pathname), mode, dev);
}

/* ========================================================================
 * Archive extraction support (used by dpkg-deb / tar)
 * ======================================================================== */

int chown32(const char *pathname, uid_t owner, gid_t group)
{
    GET_REAL(chown);
    return real_chown(T1(pathname), owner, group);
}

/* Some Android bionic versions use __fchmodat */
int __fchmodat(int dirfd, const char *pathname, mode_t mode, int flags)
{
    static __typeof__(__fchmodat) *real_fn = NULL;
    if (!real_fn) real_fn = dlsym(RTLD_NEXT, "__fchmodat");
    if (!real_fn) return -1;
    return real_fn(dirfd, T1(pathname), mode, flags);
}

/* __fstatat64 is the actual bionic internal symbol for fstatat */
int __fstatat64(int dirfd, const char *pathname, struct stat64 *statbuf, int flags)
{
    static __typeof__(__fstatat64) *real_fn = NULL;
    if (!real_fn) real_fn = dlsym(RTLD_NEXT, "__fstatat64");
    if (!real_fn) return -1;
    return real_fn(dirfd, T1(pathname), statbuf, flags);
}

/* ========================================================================
 * File descriptor tracking for *at() syscalls (advanced)
 *
 * When dpkg uses openat() with a dirfd that points to a directory
 * under /data/data/com.termux/, and a relative pathname, the
 * translation of the pathname alone may not be sufficient.
 *
 * We handle the common case: the pathname itself contains com.termux.
 * The dirfd case is rare in practice and would require fd-to-path
 * tracking via /proc/self/fd/ which adds significant complexity.
 * ======================================================================== */

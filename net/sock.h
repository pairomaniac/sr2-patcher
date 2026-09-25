/*
 * sock.h - the little of UDP the core needs, Winsock or BSD.
 *
 * Non-blocking sockets, broadcast allowed, addresses as (network-order
 * IPv4, host-order port). Header-only so the core and the test build alike.
 */
#ifndef SR2_SOCK_H
#define SR2_SOCK_H

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
#include <mstcpip.h>
#ifndef SIO_UDP_CONNRESET
#define SIO_UDP_CONNRESET _WSAIOW(IOC_VENDOR, 12)
#endif
typedef SOCKET sock_t;
#define SOCK_INVALID INVALID_SOCKET
#else
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <netdb.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <pthread.h>
typedef int sock_t;
#define SOCK_INVALID (-1)
#endif

typedef struct {
    uint32_t addr;                  /* network order */
    uint16_t port;                  /* host order */
} sock_addr;

/* A test build may drop packets here: return nonzero to lose one. */
#ifdef SR2_TEST
extern int (*sock_test_drop)(sock_t s, const sock_addr *to, const void *data, int len);
#endif

static inline int sock_addr_eq(const sock_addr *a, const sock_addr *b)
{
    return a->addr == b->addr && a->port == b->port;
}

static inline int sock_startup(void)
{
#ifdef _WIN32
    WSADATA wsa;
    return WSAStartup(MAKEWORD(2, 2), &wsa) == 0 ? 0 : -1;
#else
    return 0;
#endif
}

static inline void sock_cleanup(void)
{
#ifdef _WIN32
    WSACleanup();
#endif
}

/* Bytes nobody off the wire can guess, for the nonces and cookies: the
 * system's random source where there is one, else the clocks, the process
 * and the stack mixed. */
static inline void sock_random(uint8_t *out, int len)
{
    int i;
#ifdef _WIN32
    LARGE_INTEGER qpc;
    uint32_t seed[6], h = 2166136261u;
    QueryPerformanceCounter(&qpc);
    seed[0] = qpc.LowPart;
    seed[1] = qpc.HighPart;
    seed[2] = GetTickCount();
    seed[3] = GetCurrentProcessId();
    seed[4] = GetCurrentThreadId();
    seed[5] = (uint32_t)(uintptr_t)&qpc;
    for (i = 0; i < len; i++) {
        h ^= seed[i % 6] + i;
        h *= 16777619u;
        h ^= h >> 15;
        h *= 2246822519u;
        h ^= h >> 13;
        out[i] = (uint8_t)(h >> 24);
        seed[i % 6] = h;
    }
#else
    FILE *fh = fopen("/dev/urandom", "rb");
    if (fh) {
        size_t got = fread(out, 1, len, fh);
        fclose(fh);
        if ((int)got == len)
            return;
    }
    for (i = 0; i < len; i++)
        out[i] = (uint8_t)(rand() >> 4);
#endif
}

/* Bound to `port`, or to any port when that one is taken or port is 0;
 * the port bound comes back through *bound. */
static inline sock_t sock_open(uint16_t port, uint16_t *bound)
{
    struct sockaddr_in sa;
    int one = 1;
    socklen_t len = sizeof sa;
    sock_t s = socket(AF_INET, SOCK_DGRAM, 0);
    if (s == SOCK_INVALID)
        return s;
    setsockopt(s, SOL_SOCKET, SO_BROADCAST, (const char *)&one, sizeof one);
    memset(&sa, 0, sizeof sa);
    sa.sin_family = AF_INET;
    sa.sin_addr.s_addr = htonl(INADDR_ANY);
    sa.sin_port = htons(port);
    if (bind(s, (struct sockaddr *)&sa, sizeof sa) != 0) {
        sa.sin_port = 0;
        if (bind(s, (struct sockaddr *)&sa, sizeof sa) != 0) {
#ifdef _WIN32
            closesocket(s);
#else
            close(s);
#endif
            return SOCK_INVALID;
        }
    }
#ifdef _WIN32
    {
        u_long nb = 1;
        BOOL off = FALSE;
        DWORD got = 0;
        ioctlsocket(s, FIONBIO, &nb);
        /* an ICMP unreachable from a peer that went away would otherwise
           make the next recvfrom fail with WSAECONNRESET */
        WSAIoctl(s, SIO_UDP_CONNRESET, &off, sizeof off, NULL, 0, &got, NULL, NULL);
    }
#else
    fcntl(s, F_SETFL, fcntl(s, F_GETFL, 0) | O_NONBLOCK);
#endif
    if (bound)
        *bound = getsockname(s, (struct sockaddr *)&sa, &len) == 0 ? ntohs(sa.sin_port) : 0;
    return s;
}

static inline void sock_close(sock_t s)
{
#ifdef _WIN32
    closesocket(s);
#else
    close(s);
#endif
}

static inline int sock_send(sock_t s, const sock_addr *to, const void *data, int len)
{
    struct sockaddr_in sa;
#ifdef SR2_TEST
    if (sock_test_drop && sock_test_drop(s, to, data, len))
        return len;
#endif
    memset(&sa, 0, sizeof sa);
    sa.sin_family = AF_INET;
    sa.sin_addr.s_addr = to->addr;
    sa.sin_port = htons(to->port);
    return (int)sendto(s, (const char *)data, len, 0, (struct sockaddr *)&sa, sizeof sa);
}

/* One datagram, or -1 when there is none. */
static inline int sock_recv(sock_t s, sock_addr *from, void *buf, int len)
{
    struct sockaddr_in sa;
    socklen_t salen = sizeof sa;
    int n = (int)recvfrom(s, (char *)buf, len, 0, (struct sockaddr *)&sa, &salen);
    if (n < 0)
        return -1;
    from->addr = sa.sin_addr.s_addr;
    from->port = ntohs(sa.sin_port);
    return n;
}

/* "host" or "host:port" to an address; a name is looked up. */
static inline int sock_parse(const char *text, uint16_t default_port, sock_addr *out)
{
    char host[256];
    const char *colon = strrchr(text, ':');
    size_t n = colon ? (size_t)(colon - text) : strlen(text);
    struct hostent *he;
    if (n == 0 || n >= sizeof host)
        return -1;
    memcpy(host, text, n);
    host[n] = 0;
    if (colon) {
        long port = atol(colon + 1);
        if (port < 0 || port > 65535)
            return -1;
        out->port = port ? (uint16_t)port : default_port;
    } else
        out->port = default_port;
    out->addr = inet_addr(host);
    if (out->addr != INADDR_NONE || strcmp(host, "255.255.255.255") == 0)
        return 0;                       /* the broadcast address is what inet_addr's failure value looks like */
    he = gethostbyname(host);
    if (!he || he->h_addrtype != AF_INET || !he->h_addr_list[0])
        return -1;
    memcpy(&out->addr, he->h_addr_list[0], 4);
    return 0;
}

/* The machine's own IPv4 addresses, up to max; how many. */
static inline int sock_local(uint32_t *out, int max)
{
    char name[256];
    struct hostent *he;
    int i = 0;
    if (gethostname(name, sizeof name) != 0 || !(he = gethostbyname(name)) || he->h_addrtype != AF_INET)
        return 0;
    for (; i < max && he->h_addr_list[i]; i++)
        memcpy(&out[i], he->h_addr_list[i], 4);
    return i;
}

/* Names looked up on a thread of their own, so a slow or absent resolver
 * does not hold the caller: sock_resolve starts one, sock_resolved says
 * when it is done and hands over the addresses, and sock_resolve_drop
 * lets go of one whether or not it has finished. The block is shared
 * with the thread and freed by whichever side is last to let go. */
#define SOCK_RESOLVE_MAX 4

typedef struct {
    volatile long refs;
    volatile long done;
    char      names[SOCK_RESOLVE_MAX][256];
    int       nnames;
    uint16_t  port;
    sock_addr addrs[SOCK_RESOLVE_MAX];
    int       naddrs;
} sock_resolver;

static inline long sock_atomic_add(volatile long *v, long d)
{
#ifdef _WIN32
    return InterlockedExchangeAdd(v, d) + d;
#else
    return __sync_add_and_fetch(v, d);
#endif
}

static inline void sock_resolve_drop(sock_resolver *r)
{
    if (r && sock_atomic_add(&r->refs, -1) == 0)
        free(r);
}

#ifdef _WIN32
static inline DWORD WINAPI sock_resolve_thread(LPVOID arg)
#else
static inline void *sock_resolve_thread(void *arg)
#endif
{
    sock_resolver *r = (sock_resolver *)arg;
    int i, c = 0;
    for (i = 0; i < r->nnames; i++)
        if (sock_parse(r->names[i], r->port, &r->addrs[c]) == 0)
            c++;
    r->naddrs = c;
    sock_atomic_add(&r->done, 1);
    sock_resolve_drop(r);
    return 0;
}

static inline sock_resolver *sock_resolve(const char *const *names, int nnames, uint16_t port)
{
    sock_resolver *r = (sock_resolver *)calloc(1, sizeof *r);
    int i;
    if (!r)
        return NULL;
    for (i = 0; i < nnames && r->nnames < SOCK_RESOLVE_MAX; i++)
        if (strlen(names[i]) < sizeof r->names[0])
            strcpy(r->names[r->nnames++], names[i]);
    r->port = port;
    r->refs = 2;
#ifdef _WIN32
    {
        HANDLE h = CreateThread(NULL, 0, sock_resolve_thread, r, 0, NULL);
        if (!h) {
            free(r);
            return NULL;
        }
        CloseHandle(h);
    }
#else
    {
        pthread_t t;
        if (pthread_create(&t, NULL, sock_resolve_thread, r) != 0) {
            free(r);
            return NULL;
        }
        pthread_detach(t);
    }
#endif
    return r;
}

/* The addresses once the thread is done: how many, or -1 while it runs. */
static inline int sock_resolved(sock_resolver *r, sock_addr *out, int max)
{
    int i;
    if (!r || !sock_atomic_add(&r->done, 0))
        return -1;
    for (i = 0; i < r->naddrs && i < max; i++)
        out[i] = r->addrs[i];
    return i;
}

/* The machine's public address, asked of a STUN server (RFC 5389, a
 * binding request from a socket of its own) on a thread of its own, the
 * servers tried in turn: sock_stun_start begins it, sock_stun_result
 * says whether it is done and hands over the address, sock_stun_drop
 * lets go of it. The block is shared with the thread as the resolver's. */
#define SOCK_STUN_PORT   19302
#define SOCK_STUN_TRIES  6              /* half a second each */
#define SOCK_STUN_MAX    4

typedef struct {
    volatile long refs;
    volatile long done;
    char      servers[SOCK_STUN_MAX][64];
    int       nservers;
    uint32_t  addr;                     /* network order, 0 for none */
} sock_stun;

static inline void sock_stun_drop(sock_stun *st)
{
    if (st && sock_atomic_add(&st->refs, -1) == 0)
        free(st);
}

static inline int sock_stun_ask(const char *server, uint32_t *addr)
{
    uint8_t req[20], resp[256];
    sock_addr to, from;
    uint16_t bound;
    sock_t s;
    int tries, i, found = 0;
    if (sock_parse(server, SOCK_STUN_PORT, &to) != 0)
        return 0;
    s = sock_open(0, &bound);
    if (s == SOCK_INVALID)
        return 0;
    memset(req, 0, sizeof req);         /* a binding request: type 1, no attributes, the magic cookie, an id */
    req[1] = 1;
    req[4] = 0x21; req[5] = 0x12; req[6] = 0xa4; req[7] = 0x42;
    sock_random(req + 8, 12);
    for (tries = 0; tries < SOCK_STUN_TRIES && !found; tries++) {
        fd_set rd;
        struct timeval tv;
        int n;
        sock_send(s, &to, req, sizeof req);
        FD_ZERO(&rd);
        FD_SET(s, &rd);
        tv.tv_sec = 0;
        tv.tv_usec = 500000;
        if (select((int)s + 1, &rd, NULL, NULL, &tv) <= 0)
            continue;
        n = sock_recv(s, &from, resp, sizeof resp);
        if (n < 20 || resp[0] != 1 || resp[1] != 1 || memcmp(resp + 4, req + 4, 16) != 0)
            continue;                   /* not a binding response to this request */
        for (i = 20; i + 4 <= n && !found; ) {
            int type = (resp[i] << 8) | resp[i + 1], len = (resp[i + 2] << 8) | resp[i + 3];
            const uint8_t *v = resp + i + 4;
            if (i + 4 + len > n)
                break;
            if ((type == 0x0020 || type == 0x0001) && len >= 8 && v[1] == 1) {   /* XOR-MAPPED-ADDRESS, MAPPED-ADDRESS, IPv4 */
                memcpy(addr, v + 4, 4);
                if (type == 0x0020)
                    *addr ^= *(const uint32_t *)(req + 4);
                found = 1;
            }
            i += 4 + ((len + 3) & ~3);
        }
    }
    sock_close(s);
    return found;
}

#ifdef _WIN32
static inline DWORD WINAPI sock_stun_thread(LPVOID arg)
#else
static inline void *sock_stun_thread(void *arg)
#endif
{
    sock_stun *st = (sock_stun *)arg;
    uint32_t addr = 0;
    int i;
    for (i = 0; i < st->nservers && !addr; i++)
        sock_stun_ask(st->servers[i], &addr);
    st->addr = addr;
    sock_atomic_add(&st->done, 1);
    sock_stun_drop(st);
    return 0;
}

static inline sock_stun *sock_stun_start(const char *const *servers)
{
    sock_stun *st = (sock_stun *)calloc(1, sizeof *st);
    int i;
    if (!st)
        return NULL;
    for (i = 0; servers[i] && st->nservers < SOCK_STUN_MAX; i++)
        if (strlen(servers[i]) < sizeof st->servers[0])
            strcpy(st->servers[st->nservers++], servers[i]);
    st->refs = 2;
#ifdef _WIN32
    {
        HANDLE h = CreateThread(NULL, 0, sock_stun_thread, st, 0, NULL);
        if (!h) {
            free(st);
            return NULL;
        }
        CloseHandle(h);
    }
#else
    {
        pthread_t t;
        if (pthread_create(&t, NULL, sock_stun_thread, st) != 0) {
            free(st);
            return NULL;
        }
        pthread_detach(t);
    }
#endif
    return st;
}

/* 1 with the address once the thread has one, 0 when it found none, -1
 * while it runs or when there is no lookup. */
static inline int sock_stun_result(sock_stun *st, uint32_t *addr)
{
    if (!st || !sock_atomic_add(&st->done, 0))
        return -1;
    if (!st->addr)
        return 0;
    *addr = st->addr;
    return 1;
}

#endif

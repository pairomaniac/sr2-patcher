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
    if (getsockname(s, (struct sockaddr *)&sa, &len) == 0 && bound)
        *bound = ntohs(sa.sin_port);
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
    out->port = colon ? (uint16_t)atoi(colon + 1) : default_port;
    if (out->port == 0)
        out->port = default_port;
    out->addr = inet_addr(host);
    if (out->addr != INADDR_NONE)
        return 0;
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
    for (; he->h_addr_list[i] && i < max; i++)
        memcpy(&out[i], he->h_addr_list[i], 4);
    return i;
}

#endif

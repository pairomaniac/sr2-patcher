/*
 * sr2net.h - the network core behind the replacement MGNetWk.dll.
 *
 * Plain UDP in a star: guests talk to the host, the host forwards. What the
 * game sees is the session/player model the stock DLL gave it (see
 * docs/NETWORK.md); com.c wraps this in the three COM objects. Nothing here
 * is Windows-specific: the caller passes the clock in, sockets go through
 * sock.h, and tools/nettest.c runs a host and guests in one process.
 */
#ifndef SR2NET_H
#define SR2NET_H

#include <stdint.h>

#define SR2_PORT            47626   /* the game; the directory is SR2_PORT+1 */
#define SR2_DIRECTORIES     {"segaonline.net", "us.segaonline.net", "jp.segaonline.net", 0}
#define SR2_MAX_PLAYERS     4
#define SR2_NAME_LEN        64      /* the game's name fields, NUL included */
#define SR2_MAX_PAYLOAD     1024    /* the game's largest message is 0x134, 0x136 with the stock DLL's header */
#define SR2_MAX_SESSIONS    16
#define SR2_PROTO           1       /* the wire's version: in the join, the welcome and the session record; a mismatch is refused */

/* OpenConnection kinds as the exe passes them: rows 0, 1, 2 of the screen. */
#define SR2_KIND_DIRECT     1       /* an address typed; empty = LAN search */
#define SR2_KIND_INTERNET   2       /* the directory server */
#define SR2_KIND_LAN        3       /* broadcast search */

/* Events, as the exe's table expects them. */
#define SR2_EV_HOST         0       /* a = the host's index */
#define SR2_EV_CREATED      1       /* a = the player's index */
#define SR2_EV_DESTROYED    2       /* a = the player's index */
#define SR2_EV_LOST         3       /* the session is gone */

/* Return codes. */
#define SR2_OK              0
#define SR2_ERR             (-1)    /* failed */
#define SR2_CONNECTING      (-2)    /* not yet: keep calling */
#define SR2_REFUSED         (-3)    /* the host said no: full, closed, not that session, or another version */
#define SR2_NONE            1       /* nothing there */
#define SR2_TOOSMALL        2       /* the buffer: *len says how much */

typedef struct {
    uint8_t  guid[16];
    int      max_players;
    int      players;
    int      closed;                /* joins refused */
    int      version;               /* the host's SR2_PROTO; 0 from a host older than it */
    char     name[SR2_NAME_LEN];
    uint32_t addr;                  /* the host, network order */
    uint16_t port;                  /* host order */
} sr2_session;

typedef struct {
    int      index;                 /* 0..SR2_MAX_PLAYERS-1 */
    int      host;
    int      local;
    char     name[SR2_NAME_LEN];
} sr2_player;

typedef struct {
    int type;
    int a;
} sr2_event;

typedef struct sr2_net sr2_net;

sr2_net *sr2_create(void);
void     sr2_destroy(sr2_net *n);

/* The socket bound and the way in chosen. address is the entry text for
 * SR2_KIND_DIRECT (host, or host:port; empty for a LAN search), the
 * directory server for SR2_KIND_INTERNET (empty for the default), and
 * ignored for SR2_KIND_LAN. */
int  sr2_open(sr2_net *n, int kind, const char *address, uint32_t now);
int  sr2_kind(const sr2_net *n);
uint16_t sr2_port(const sr2_net *n);

/* Where a LAN search goes: the broadcast address by default; the test
 * points it at loopback. sr2_set_directory replaces the directory servers
 * with one, for the test. */
void sr2_set_search(sr2_net *n, uint32_t addr, uint16_t port);
void sr2_set_directory(sr2_net *n, uint32_t addr, uint16_t port);

/* Sessions found so far, asked for again every call; SR2_CONNECTING until
 * the first answer or the wait is up, then the count. */
int  sr2_enum(sr2_net *n, uint32_t now, sr2_session *out, int max);

/* A session of ours, or a place in someone's. A join is asked for and
 * then followed up every poll: SR2_CONNECTING while the host has not
 * answered, then SR2_OK, SR2_REFUSED (full, closed, or not that session)
 * or SR2_ERR (no answer in a few seconds). */
int  sr2_host(sr2_net *n, const char *name, int max_players, uint32_t now);
int  sr2_join(sr2_net *n, const sr2_session *s, uint32_t now);
int  sr2_join_status(sr2_net *n, uint32_t now);
void sr2_leave(sr2_net *n, uint32_t now);
int  sr2_in_session(const sr2_net *n);
int  sr2_is_host(const sr2_net *n);

/* The local player: the index the host gave (the join brought it), the
 * name told to everyone. Events HOST and CREATED follow through poll. */
int  sr2_player_create(sr2_net *n, const char *name, uint32_t now);
int  sr2_my_index(const sr2_net *n);

void sr2_set_open(sr2_net *n, int open, uint32_t now);
int  sr2_session_info(const sr2_net *n, sr2_session *out);
int  sr2_player_count(const sr2_net *n, int *max, int *current);
int  sr2_player_info(const sr2_net *n, int index, sr2_player *out);
int  sr2_slot_reserved(const sr2_net *n, int index);
int  sr2_slot_reserve(sr2_net *n, int index, int on, uint32_t now);   /* host only */

/* Once a frame: the socket drained, the timers run, the lists kept.
 * SR2_ERR when the session is lost (an SR2_EV_LOST event is queued too). */
int  sr2_poll(sr2_net *n, uint32_t now);
int  sr2_pop_event(sr2_net *n, sr2_event *ev);

/* Game messages: to an index, or -1 for everyone else; reliable ones
 * arrive in order, resent until acknowledged and held back while the
 * receiver's queue is full; the others when they do. SR2_ERR when a
 * reliable one cannot be sent: 64 unacknowledged already on that link
 * after the socket has been drained, which a live peer never reaches. */
int  sr2_send(sr2_net *n, int to, const void *data, int len, int reliable, uint32_t now);
int  sr2_recv(sr2_net *n, int *from, void *buf, int *len);

/* A line for the team room's status strip: our address and port. */
const char *sr2_status(sr2_net *n);

/* Diagnostics: a log line sink, NULL for none. */
void sr2_set_log(sr2_net *n, void (*fn)(void *ctx, const char *line), void *ctx);

#endif

/*
 * sr2net.c - the network core: sessions, players, a reliable and an
 * unreliable class of message, over UDP in a star.
 *
 * Wire: every datagram is a 16-byte header and a payload.
 *
 *   0  "SR2N"
 *   4  type
 *   5  flags        bit 0: reliable
 *   6  from         the sender's index, 0xff before it has one
 *   7  to           an index, 0xff for everyone
 *   8  seq  u32     the reliable sequence, 0 otherwise
 *  12  ack  u32     the last reliable sequence taken in order from the peer
 *
 * Reliable messages are numbered per link, acknowledged on arrival, sent
 * again every RESEND_MS until they are, and delivered in order; a link
 * with nothing acknowledged for DEAD_MS, or nothing heard for as long, is
 * gone. Guests have one link, to the host; the host one per guest, and
 * forwards between them. The host owns the player list: it assigns the
 * indices and sends the roster on every change.
 *
 * A join names the session, an eight-byte nonce (the guest's identity
 * across a change of address), the wire version and a cookie: the host
 * answers a join without its cookie with T_CHALLENGE carrying it, so a
 * forged source address never gets a seat or a reply worth reflecting.
 * The welcome and the session record carry the version too, and each
 * link keeps the one the other side gave; a peer from before the
 * version, which sends none, is refused with a reason.
 *
 * The directory speaks "SR2E": op, a four-byte token the client made
 * up, then the body; the server echoes the token in every answer and the
 * client takes no answer without it.
 */
#include "sr2net.h"
#include "sock.h"

#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define HDR             16
#define WINDOW          64
#define QUEUE           128
#define EVENTS          64
#define RESEND_MS       250
#define PING_MS         500
#define DEAD_MS         12000   /* silence that ends a link: past a stage load with the game not polling */
#define QUERY_MS        400
#define SESSION_TTL_MS  3000
#define ENUM_WAIT_MS    3000
#define JOIN_WAIT_MS    5000
#define JOIN_RETRY_MS   300
#define PUNCH_MS        4000    /* direct tries before the relay */
#define REGISTER_MS     1000    /* a host's refresh at the directory */
#define MAX_SERVERS     4
#define DMAGIC          "SR2E"
#define DHDR            9       /* magic, op, token */
#define JOIN_LEN        29      /* guid, nonce, version, cookie */
#define QUERY_RATE      25      /* T_QUERY answers a second, a host's ceiling */

enum {
    T_QUERY = 1,        /* who is hosting? */
    T_SESSION,          /* a host's record: max, players, closed, guid, name */
    T_JOIN,             /* guest -> host: guid */
    T_WELCOME,          /* host -> guest, reliable: your index, the reserved table, the roster */
    T_REFUSE,           /* host -> guest: reason */
    T_NAME,             /* guest -> host, reliable: my name */
    T_ROSTER,           /* host -> guests, reliable: count, {index, host, name}... */
    T_SLOTS,            /* host -> guests, reliable: the reserved table */
    T_LEAVE,            /* either way */
    T_PING,             /* keep-alive */
    T_PONG,
    T_ACK,              /* nothing but the ack field */
    T_GAME,             /* the game's message */
    T_PUNCH,            /* opens a NAT; ignored */
    T_CHALLENGE         /* host -> guest: the cookie a join from that address needs */
};

#define F_RELIABLE      1
#define NOBODY          0xff

typedef struct {
    uint32_t seq;
    uint32_t sent;                  /* last time out */
    uint32_t first;                 /* first time out */
    int      len;                   /* 0 = free */
    uint8_t  data[HDR + SR2_MAX_PAYLOAD];
} rmsg;

/* Where a datagram goes: straight to addr, or wrapped to the directory
 * server at `via`, which forwards it; addr is then the peer's public
 * address as that server sees it, the token the server needs back. */
typedef struct {
    sock_addr addr;
    int       relayed;
    sock_addr via;
} route;

typedef struct {
    int       used;
    route     rt;
    uint8_t   nonce[8];             /* the join's, so a second route to one guest is one guest */
    int       index;                /* the player at the other end, -1 until known */
    int       version;              /* the wire version it gave */
    uint32_t  send_seq;             /* last reliable sequence sent */
    uint32_t  recv_seq;             /* last taken in order */
    rmsg      unacked[WINDOW];      /* by seq % WINDOW */
    int       nunacked;
    rmsg      held[WINDOW];         /* arrived early, by seq % WINDOW */
    uint32_t  last_heard;
    uint32_t  last_sent;
} peer;

typedef struct {
    int  used;
    int  host;
    int  local;
    char name[SR2_NAME_LEN];
} player;

typedef struct {
    int     from;
    int     len;
    uint8_t data[SR2_MAX_PAYLOAD];
} qmsg;

struct sr2_net {
    sock_t    sock;
    uint16_t  port;
    int       kind;
    sock_addr target;               /* direct: the host typed; lan: where the search goes */
    int       have_target;
    int       bad_target;           /* direct: the text typed was not an address; the search fails, hosting does not need it */
    sock_addr servers[MAX_SERVERS]; /* the directory, SR2_KIND_INTERNET */
    int       nservers;
    sock_resolver *resolving;       /* the servers' names being looked up, off the game's thread */
    uint32_t  dcookie[MAX_SERVERS]; /* what each server's challenge to a registration said, 0 before it */
    uint32_t  last_register;
    sock_addr relay;                /* the server the join went through */
    uint8_t   join_nonce[8];
    uint32_t  join_cookie;          /* what the host's challenge said, 0 before it */
    uint32_t  secret;               /* the host's: its cookies are made from it */
    uint32_t  dtoken;               /* the directory token, made up at open */
    uint32_t  query_tokens, query_last;     /* the T_QUERY answers' bucket */
    /* search */
    int       searching;
    uint32_t  search_start, last_query;
    sr2_session found[SR2_MAX_SESSIONS];
    uint32_t  found_at[SR2_MAX_SESSIONS];
    sock_addr found_via[SR2_MAX_SESSIONS];
    int       nfound;
    /* session */
    int       in_session, is_host, lost;
    int       joining, join_refused;    /* the join in progress, and how it ended */
    uint32_t  join_start, join_last;
    int       announced;                /* the local player exists: rosters make events */
    uint8_t   guid[16];
    char      session_name[SR2_NAME_LEN];
    int       max_players, open;
    int       my_index;
    player    players[SR2_MAX_PLAYERS];
    uint8_t   reserved[SR2_MAX_PLAYERS];
    peer      peers[SR2_MAX_PLAYERS];   /* host: by guest index; guest: [0] is the host */
    /* queues */
    sr2_event events[EVENTS];
    int       ev_head, ev_count;
    qmsg      queue[QUEUE];
    int       q_head, q_count;
    char      status[128];
    uint32_t  rnd;
    void    (*log)(void *, const char *);
    void     *log_ctx;
};

#ifdef SR2_TEST
int (*sock_test_drop)(sock_t s, const sock_addr *to, const void *data, int len);
#endif

static void nlog(sr2_net *n, const char *fmt, ...)
{
    char line[256];
    va_list ap;
    if (!n->log)
        return;
    va_start(ap, fmt);
    vsnprintf(line, sizeof line, fmt, ap);
    va_end(ap);
    n->log(n->log_ctx, line);
}

static uint32_t rd32(const uint8_t *p) { return p[0] | p[1] << 8 | p[2] << 16 | (uint32_t)p[3] << 24; }
static void wr32(uint8_t *p, uint32_t v) { p[0] = v; p[1] = v >> 8; p[2] = v >> 16; p[3] = v >> 24; }

static uint32_t rnd(sr2_net *n)
{
    n->rnd = n->rnd * 1103515245u + 12345u;
    return n->rnd;
}

/* The cookie a join from `from` needs: the host's secret and the address
 * mixed, nothing kept per address. */
static uint32_t cookie_for(const sr2_net *n, const sock_addr *from)
{
    uint32_t h = n->secret ^ from->addr ^ ((uint32_t)from->port << 16) ^ 0x9e3779b9u;
    h ^= h >> 16; h *= 0x85ebca6bu;
    h ^= h >> 13; h *= 0xc2b2ae35u;
    h ^= h >> 16;
    return h ? h : 1;
}

/* A directory datagram's head: magic, op, the token. */
static int dhead(const sr2_net *n, uint8_t *buf, char op)
{
    memcpy(buf, DMAGIC, 4);
    buf[4] = op;
    wr32(buf + 5, n->dtoken);
    return DHDR;
}

static void copy_name(char *dst, const char *src)
{
    size_t i = 0;
    for (; src && src[i] && i < SR2_NAME_LEN - 1; i++)
        dst[i] = src[i];
    dst[i] = 0;
}

/* --- events and the game queue --- */

static void push_event(sr2_net *n, int type, int a)
{
    sr2_event *ev;
    if (n->ev_count == EVENTS)
        return;
    ev = &n->events[(n->ev_head + n->ev_count++) % EVENTS];
    ev->type = type;
    ev->a = a;
}

int sr2_pop_event(sr2_net *n, sr2_event *ev)
{
    if (!n->ev_count)
        return SR2_NONE;
    *ev = n->events[n->ev_head];
    n->ev_head = (n->ev_head + 1) % EVENTS;
    n->ev_count--;
    return SR2_OK;
}

static void queue_game(sr2_net *n, int from, const uint8_t *data, int len)
{
    qmsg *m;
    if (n->q_count == QUEUE || len > SR2_MAX_PAYLOAD) {
        nlog(n, "queue full: a message from %d dropped", from);
        return;
    }
    m = &n->queue[(n->q_head + n->q_count++) % QUEUE];
    m->from = from;
    m->len = len;
    memcpy(m->data, data, len);
}

int sr2_recv(sr2_net *n, int *from, void *buf, int *len)
{
    qmsg *m;
    if (!n->q_count) {
        *len = 0;
        return SR2_NONE;
    }
    m = &n->queue[n->q_head];
    if (!buf || *len < m->len) {
        *len = m->len;
        return SR2_TOOSMALL;
    }
    memcpy(buf, m->data, m->len);
    *len = m->len;
    *from = m->from;
    n->q_head = (n->q_head + 1) % QUEUE;
    n->q_count--;
    return SR2_OK;
}

/* --- the wire --- */

static int my_index_byte(const sr2_net *n) { return n->my_index < 0 ? NOBODY : n->my_index; }

/* A datagram out along a route: as it is, or wrapped for the relay. */
static void emit(sr2_net *n, const route *to, const void *data, int len)
{
    uint8_t wrap[DHDR + 16 + 6 + HDR + SR2_MAX_PAYLOAD];
    int pos;
    if (!to->relayed) {
        sock_send(n->sock, &to->addr, data, len);
        return;
    }
    dhead(n, wrap, 'R');
    memcpy(wrap + DHDR, n->guid, 16);
    pos = DHDR + 16;
    if (n->is_host) {                   /* the guest's token: its address as the server sees it */
        memcpy(wrap + pos, &to->addr.addr, 4);
        wrap[pos + 4] = to->addr.port >> 8;
        wrap[pos + 5] = to->addr.port & 0xff;
        pos += 6;
    }
    memcpy(wrap + pos, data, len);
    sock_send(n->sock, &to->via, wrap, pos + len);
}

static void send_raw(sr2_net *n, const route *to, int type, int from, int dest,
                     uint32_t ack, const void *payload, int len)
{
    uint8_t pkt[HDR + SR2_MAX_PAYLOAD];
    if (len > SR2_MAX_PAYLOAD)
        return;
    memcpy(pkt, "SR2N", 4);
    pkt[4] = type;
    pkt[5] = 0;
    pkt[6] = from;
    pkt[7] = dest;
    wr32(pkt + 8, 0);
    wr32(pkt + 12, ack);
    if (len)
        memcpy(pkt + HDR, payload, len);
    emit(n, to, pkt, HDR + len);
}

/* Unreliable, over a link. */
static void send_to(sr2_net *n, peer *p, int type, int dest, const void *payload, int len, uint32_t now)
{
    send_raw(n, &p->rt, type, my_index_byte(n), dest, p->recv_seq, payload, len);
    p->last_sent = now;
}

/* Reliable, over a link: numbered, kept until acknowledged. */
static int send_reliable(sr2_net *n, peer *p, int type, int from, int dest, const void *payload, int len, uint32_t now)
{
    rmsg *m;
    if (p->nunacked == WINDOW || len > SR2_MAX_PAYLOAD) {
        nlog(n, "link %d: window full, a %d-byte message not sent", p->index, len);
        return SR2_ERR;
    }
    p->send_seq++;
    m = &p->unacked[p->send_seq % WINDOW];
    m->seq = p->send_seq;
    m->first = m->sent = now;
    m->len = HDR + len;
    memcpy(m->data, "SR2N", 4);
    m->data[4] = type;
    m->data[5] = F_RELIABLE;
    m->data[6] = from;
    m->data[7] = dest;
    wr32(m->data + 8, m->seq);
    wr32(m->data + 12, p->recv_seq);
    if (len)
        memcpy(m->data + HDR, payload, len);
    p->nunacked++;
    emit(n, &p->rt, m->data, m->len);
    p->last_sent = now;
    return SR2_OK;
}

static void peer_reset(peer *p, const route *rt, int index, uint32_t now)
{
    memset(p, 0, sizeof *p);
    p->used = 1;
    p->rt = *rt;
    p->index = index;
    p->last_heard = p->last_sent = now;
}

static peer *peer_by_addr(sr2_net *n, const sock_addr *addr)
{
    int i;
    for (i = 0; i < SR2_MAX_PLAYERS; i++)
        if (n->peers[i].used && sock_addr_eq(&n->peers[i].rt.addr, addr))
            return &n->peers[i];
    return NULL;
}

/* --- the session record and the roster --- */

static int count_players(const sr2_net *n)
{
    int i, c = 0;
    for (i = 0; i < SR2_MAX_PLAYERS; i++)
        c += n->players[i].used;
    return c;
}

static int free_index(const sr2_net *n)
{
    int i;
    for (i = 0; i < n->max_players; i++)
        if (!n->players[i].used && !n->reserved[i])
            return i;
    return -1;
}

/* The record the directory keeps: max, players, closed, name[64]. */
static int pack_record(const sr2_net *n, uint8_t *out)
{
    out[0] = n->max_players;
    out[1] = count_players(n);
    out[2] = !n->open || free_index(n) < 0;
    memcpy(out + 3, n->session_name, SR2_NAME_LEN);
    return 3 + SR2_NAME_LEN;
}

/* T_SESSION: max, players, closed, guid[16], name[64], version. */
static int pack_session(const sr2_net *n, uint8_t *out)
{
    out[0] = n->max_players;
    out[1] = count_players(n);
    out[2] = !n->open || free_index(n) < 0;
    memcpy(out + 3, n->guid, 16);
    memcpy(out + 19, n->session_name, SR2_NAME_LEN);
    out[19 + SR2_NAME_LEN] = SR2_PROTO;
    return 20 + SR2_NAME_LEN;
}

/* The roster: count, then {index, host, name[64]} each. */
static int pack_roster(const sr2_net *n, uint8_t *out)
{
    int i, len = 1, c = 0;
    for (i = 0; i < SR2_MAX_PLAYERS; i++) {
        if (!n->players[i].used)
            continue;
        out[len++] = i;
        out[len++] = n->players[i].host;
        memcpy(out + len, n->players[i].name, SR2_NAME_LEN);
        len += SR2_NAME_LEN;
        c++;
    }
    out[0] = c;
    return len;
}

/* A guest takes the host's roster: players that appeared or went become
 * events, names are refreshed. */
static void take_roster(sr2_net *n, const uint8_t *data, int len)
{
    player fresh[SR2_MAX_PLAYERS];
    int i, c, pos = 1;
    if (len < 1)
        return;
    c = data[0];
    memset(fresh, 0, sizeof fresh);
    for (i = 0; i < c && pos + 2 + SR2_NAME_LEN <= len; i++) {
        int idx = data[pos];
        if (idx < SR2_MAX_PLAYERS) {
            fresh[idx].used = 1;
            fresh[idx].host = data[pos + 1] != 0;
            fresh[idx].local = idx == n->my_index;
            memcpy(fresh[idx].name, data + pos + 2, SR2_NAME_LEN);
            fresh[idx].name[SR2_NAME_LEN - 1] = 0;
        }
        pos += 2 + SR2_NAME_LEN;
    }
    for (i = 0; i < SR2_MAX_PLAYERS; i++) {
        if (n->players[i].used && !fresh[i].used && n->announced)
            push_event(n, SR2_EV_DESTROYED, i);
    }
    for (i = 0; i < SR2_MAX_PLAYERS; i++) {
        int was = n->players[i].used;
        n->players[i] = fresh[i];
        if (fresh[i].used && !was && n->announced)
            push_event(n, SR2_EV_CREATED, i);
    }
}

static void host_broadcast_reliable(sr2_net *n, int type, const void *payload, int len, uint32_t now)
{
    int i;
    for (i = 0; i < SR2_MAX_PLAYERS; i++)
        if (n->peers[i].used && n->peers[i].index >= 0)
            send_reliable(n, &n->peers[i], type, my_index_byte(n), NOBODY, payload, len, now);
}

static void host_send_roster(sr2_net *n, uint32_t now)
{
    uint8_t buf[1 + SR2_MAX_PLAYERS * (2 + SR2_NAME_LEN)];
    int len = pack_roster(n, buf);
    host_broadcast_reliable(n, T_ROSTER, buf, len, now);
}

/* The host drops a guest: its player, its link, the others told. */
static void host_drop(sr2_net *n, int index, const char *why, uint32_t now)
{
    if (index < 0 || index >= SR2_MAX_PLAYERS || !n->players[index].used || n->players[index].local)
        return;
    nlog(n, "player %d (%s) gone: %s", index, n->players[index].name, why);
    if (n->peers[index].used) {
        send_to(n, &n->peers[index], T_LEAVE, NOBODY, NULL, 0, now);
        n->peers[index].used = 0;
    }
    memset(&n->players[index], 0, sizeof(player));
    push_event(n, SR2_EV_DESTROYED, index);
    host_send_roster(n, now);
}

static void session_lost(sr2_net *n, const char *why)
{
    int i;
    if (n->lost)
        return;
    nlog(n, "session lost: %s", why);
    n->lost = 1;
    for (i = 0; i < SR2_MAX_PLAYERS; i++)
        n->peers[i].used = 0;
    push_event(n, SR2_EV_LOST, 0);
}

/* --- the reliable link: acks, ordering, and what arrives --- */

static void handle_message(sr2_net *n, peer *p, const uint8_t *pkt, int len, uint32_t now);

static void take_ack(peer *p, uint32_t ack)
{
    int i;
    if ((int32_t)(ack - p->send_seq) > 0)
        return;                         /* nothing that high was sent: forged or garbage */
    for (i = 0; i < WINDOW && p->nunacked; i++) {
        rmsg *m = &p->unacked[i];
        if (m->len && (int32_t)(m->seq - ack) <= 0) {
            m->len = 0;
            p->nunacked--;
        }
    }
}

/* A game message for this side needs a place in the queue; a reliable
 * one without it is left unacknowledged, so the sender sends it again. */
static int room_for(const sr2_net *n, const uint8_t *pkt)
{
    int dest = pkt[7];
    if (pkt[4] != T_GAME || n->q_count < QUEUE)
        return 1;
    return n->is_host && dest != NOBODY && dest != n->my_index;
}

/* A reliable packet in: in order, held for later, or a duplicate. */
static void take_reliable(sr2_net *n, peer *p, const uint8_t *pkt, int len, uint32_t now)
{
    uint32_t seq = rd32(pkt + 8);
    int32_t ahead = (int32_t)(seq - p->recv_seq);
    if (ahead <= 0) {
        /* seen already; the ack below says so again */
    } else if (ahead == 1 && room_for(n, pkt)) {
        p->recv_seq = seq;
        handle_message(n, p, pkt, len, now);
        for (;;) {
            rmsg *h = &p->held[(p->recv_seq + 1) % WINDOW];
            int hlen = h->len;
            if (!p->used || !hlen || h->seq != p->recv_seq + 1 || !room_for(n, h->data))
                break;                  /* a leave handled above ends the link: nothing more from it */
            p->recv_seq++;
            h->len = 0;
            handle_message(n, p, h->data, hlen, now);
        }
    } else if (ahead == 1) {
        /* no room: not taken, not acknowledged; it comes again */
    } else if (ahead <= WINDOW) {
        rmsg *h = &p->held[seq % WINDOW];
        if (!h->len) {
            h->seq = seq;
            h->len = len;
            memcpy(h->data, pkt, len);
        }
    }
    send_raw(n, &p->rt, T_ACK, my_index_byte(n), NOBODY, p->recv_seq, NULL, 0);
}

/* --- what the messages mean --- */

static void host_take_join(sr2_net *n, const route *from, const uint8_t *pkt, int len, uint32_t now)
{
    peer *p = peer_by_addr(n, &from->addr);
    uint8_t buf[2 + SR2_MAX_PLAYERS + 1 + SR2_MAX_PLAYERS * (2 + SR2_NAME_LEN) + 1];
    int idx, blen, i;
    uint8_t reason;
    const uint8_t *nonce;
    uint32_t cookie, want;
    if (len < HDR + 16 || memcmp(pkt + HDR, n->guid, 16) != 0) {
        reason = 1;                     /* not this session */
        send_raw(n, from, T_REFUSE, my_index_byte(n), NOBODY, 0, &reason, 1);
        return;
    }
    if (len < HDR + JOIN_LEN || pkt[HDR + 24] < SR2_PROTO_MIN) {
        reason = 4;                     /* from before the wire's version: a guest of 0.7.0 sends 20 bytes */
        nlog(n, "a join from before the wire's version (%d) from %08x:%u refused",
             len < HDR + JOIN_LEN ? 0 : pkt[HDR + 24], ntohl(from->addr.addr), from->addr.port);
        send_raw(n, from, T_REFUSE, my_index_byte(n), NOBODY, 0, &reason, 1);
        return;
    }
    nonce = pkt + HDR + 16;
    cookie = rd32(pkt + HDR + 25);
    if (!p)                             /* the same guest by another road: a NAT gave it another address, or a direct join reached a relayed one */
        for (i = 0; i < SR2_MAX_PLAYERS; i++)
            if (n->peers[i].used && memcmp(n->peers[i].nonce, nonce, 8) == 0) {
                p = &n->peers[i];
                nlog(n, "player %d now %s", p->index, from->relayed ? "relayed" : "direct");
                p->rt = *from;
                p->unacked[1 % WINDOW].sent = 0;
                break;
            }
    if (p) {
        idx = p->index;                 /* a join sent again: the welcome again */
        if (from->relayed && !p->rt.relayed)
            p->rt = *from;              /* the guest gave up on the direct road */
    } else {
        want = cookie_for(n, &from->addr);
        if (cookie != want) {           /* a first join, or a forged address: the cookie, and nothing else */
            uint8_t c[4];
            wr32(c, want);
            send_raw(n, from, T_CHALLENGE, my_index_byte(n), NOBODY, 0, c, 4);
            return;
        }
        if (!n->open) {
            reason = 2;
            send_raw(n, from, T_REFUSE, my_index_byte(n), NOBODY, 0, &reason, 1);
            return;
        }
        idx = free_index(n);
        if (idx < 0) {
            reason = 3;
            send_raw(n, from, T_REFUSE, my_index_byte(n), NOBODY, 0, &reason, 1);
            return;
        }
        p = &n->peers[idx];
        peer_reset(p, from, idx, now);
        memcpy(p->nonce, nonce, 8);
        p->version = pkt[HDR + 24];
        memset(&n->players[idx], 0, sizeof(player));
        n->players[idx].used = 1;
        nlog(n, "player %d joined from %08x:%u%s", idx, ntohl(from->addr.addr), from->addr.port,
             from->relayed ? " through the relay" : "");
        push_event(n, SR2_EV_CREATED, idx);
    }
    if (p->send_seq == 0) {
        buf[0] = idx;
        buf[1] = n->my_index;
        memcpy(buf + 2, n->reserved, SR2_MAX_PLAYERS);
        blen = 2 + SR2_MAX_PLAYERS + pack_roster(n, buf + 2 + SR2_MAX_PLAYERS);
        buf[blen++] = SR2_PROTO;
        send_reliable(n, p, T_WELCOME, my_index_byte(n), idx, buf, blen, now);
        host_send_roster(n, now);       /* the others (and the newcomer again, harmlessly) */
    } else {                            /* the welcome is on its way: send it again now */
        rmsg *m = &n->peers[idx].unacked[1 % WINDOW];
        if (m->len && m->seq == 1)
            m->sent = 0;
    }
}

static void handle_message(sr2_net *n, peer *p, const uint8_t *pkt, int len, uint32_t now)
{
    int type = pkt[4], dest = pkt[7];
    const uint8_t *body = pkt + HDR;
    int blen = len - HDR;
    switch (type) {
    case T_GAME:
        if (n->is_host) {
            int from = p->index;
            if (dest == NOBODY || dest == n->my_index)
                queue_game(n, from, body, blen);
            if (dest == NOBODY) {
                int i;
                for (i = 0; i < SR2_MAX_PLAYERS; i++)
                    if (n->peers[i].used && n->peers[i].index >= 0 && &n->peers[i] != p) {
                        if (pkt[5] & F_RELIABLE)
                            send_reliable(n, &n->peers[i], T_GAME, from, dest, body, blen, now);
                        else
                            send_raw(n, &n->peers[i].rt, T_GAME, from, dest, n->peers[i].recv_seq, body, blen);
                    }
            } else if (dest < SR2_MAX_PLAYERS && n->peers[dest].used && n->peers[dest].index >= 0 && &n->peers[dest] != p) {
                if (pkt[5] & F_RELIABLE)
                    send_reliable(n, &n->peers[dest], T_GAME, from, dest, body, blen, now);
                else
                    send_raw(n, &n->peers[dest].rt, T_GAME, from, dest, n->peers[dest].recv_seq, body, blen);
            }
        } else {
            queue_game(n, pkt[6], body, blen);
        }
        break;
    case T_WELCOME: {
        int rlen;
        if (n->is_host || blen < 2 + SR2_MAX_PLAYERS + 1 || body[0] >= SR2_MAX_PLAYERS || body[1] >= SR2_MAX_PLAYERS)
            break;                      /* an index past the table is no seat, the host's included */
        rlen = 1 + body[2 + SR2_MAX_PLAYERS] * (2 + SR2_NAME_LEN);     /* the roster; the version after it */
        if (blen < 2 + SR2_MAX_PLAYERS + rlen + 1 || body[2 + SR2_MAX_PLAYERS + rlen] < SR2_PROTO_MIN) {
            if (n->joining) {
                nlog(n, "the host is from before the wire's version (%d): refused",
                     blen < 2 + SR2_MAX_PLAYERS + rlen + 1 ? 0 : body[2 + SR2_MAX_PLAYERS + rlen]);
                n->join_refused = 1;
            }
            break;
        }
        p->version = body[2 + SR2_MAX_PLAYERS + rlen];
        n->my_index = body[0];
        p->index = body[1];
        memcpy(n->reserved, body + 2, SR2_MAX_PLAYERS);
        take_roster(n, body + 2 + SR2_MAX_PLAYERS, rlen);
        break;
    }
    case T_CHALLENGE:
        if (!n->is_host && n->joining && blen >= 4) {
            n->join_cookie = rd32(body);
            n->join_last = 0;           /* the join again, with it, on the next poll */
        }
        break;
    case T_ROSTER:
        if (!n->is_host)
            take_roster(n, body, blen);
        break;
    case T_SLOTS:
        if (!n->is_host && blen >= SR2_MAX_PLAYERS)
            memcpy(n->reserved, body, SR2_MAX_PLAYERS);
        break;
    case T_NAME:
        if (n->is_host && p->index >= 0 && n->players[p->index].used) {
            char name[SR2_NAME_LEN];
            memset(name, 0, sizeof name);
            memcpy(name, body, blen < SR2_NAME_LEN ? blen : SR2_NAME_LEN - 1);
            copy_name(n->players[p->index].name, name);
            host_send_roster(n, now);
        }
        break;
    case T_LEAVE:
        if (n->is_host)
            host_drop(n, p->index, "left", now);
        else
            session_lost(n, "the host left");
        break;
    case T_PING:
        send_to(n, p, T_PONG, NOBODY, NULL, 0, now);
        break;
    default:
        break;
    }
}

/* One datagram in. */
static void take_packet(sr2_net *n, const route *from, uint8_t *pkt, int len, uint32_t now)
{
    int type;
    peer *p;
    if (len < HDR || len > HDR + SR2_MAX_PAYLOAD || memcmp(pkt, "SR2N", 4) != 0)
        return;                         /* no sender makes more; a held copy has no room for it */
    type = pkt[4];
    /* outside a link: the search and the join */
    if (type == T_QUERY) {
        if (n->in_session && n->is_host && !n->lost) {
            uint8_t buf[20 + SR2_NAME_LEN];
            int blen;
            uint32_t earned = (now - n->query_last) * QUERY_RATE / 1000;
            if (earned) {
                n->query_tokens = n->query_tokens + earned > QUERY_RATE ? QUERY_RATE : n->query_tokens + earned;
                n->query_last = now;
            }
            if (!n->query_tokens)
                return;                 /* a search answered QUERY_RATE times a second at most: no reflector */
            n->query_tokens--;
            blen = pack_session(n, buf);
            send_raw(n, from, T_SESSION, my_index_byte(n), NOBODY, 0, buf, blen);
        }
        return;
    }
    if (type == T_SESSION) {
        int i, slot = -1;
        if (!n->searching || len < HDR + 19 + SR2_NAME_LEN)
            return;
        for (i = 0; i < n->nfound; i++)
            if (memcmp(n->found[i].guid, pkt + HDR + 3, 16) == 0) {
                slot = i;
                break;
            }
        if (slot < 0) {
            if (n->nfound == SR2_MAX_SESSIONS)
                return;
            slot = n->nfound++;
        }
        n->found[slot].max_players = pkt[HDR];
        n->found[slot].players = pkt[HDR + 1];
        n->found[slot].closed = pkt[HDR + 2];
        memcpy(n->found[slot].guid, pkt + HDR + 3, 16);
        memcpy(n->found[slot].name, pkt + HDR + 19, SR2_NAME_LEN);
        n->found[slot].name[SR2_NAME_LEN - 1] = 0;
        n->found[slot].addr = from->addr.addr;
        n->found[slot].port = from->addr.port;
        n->found[slot].version = len >= HDR + 20 + SR2_NAME_LEN ? pkt[HDR + 19 + SR2_NAME_LEN] : 0;
        n->found_via[slot].addr = 0;
        n->found_via[slot].port = 0;
        n->found_at[slot] = now;
        return;
    }
    if (!n->in_session || n->lost)
        return;
    if (type == T_JOIN) {
        if (n->is_host)
            host_take_join(n, from, pkt, len, now);
        return;
    }
    p = peer_by_addr(n, &from->addr);
    if (!p)
        return;
    if (from->relayed && !p->rt.relayed) {
        nlog(n, "link %d: over the relay now", p->index);
        p->rt = *from;
    }
    p->last_heard = now;
    take_ack(p, rd32(pkt + 12));
    if (type == T_REFUSE) {
        if (n->joining && len > HDR) {
            static const char *const why[] = {"?", "not that session", "closed", "full", "a patcher from before this one's wire"};
            nlog(n, "refused by the host: %s", pkt[HDR] < 5 ? why[pkt[HDR]] : "?");
            n->join_refused = 1;
        }
        return;
    }
    if (pkt[5] & F_RELIABLE)
        take_reliable(n, p, pkt, len, now);
    else
        handle_message(n, p, pkt, len, now);
}

/* Which directory server an address is, or -1. */
static int server_index(const sr2_net *n, const sock_addr *a)
{
    int i;
    for (i = 0; i < n->nservers; i++)
        if (sock_addr_eq(&n->servers[i], a))
            return i;
    return -1;
}

/* The servers' names, once the lookup is done: the list, or none. */
static void take_resolved(sr2_net *n, uint32_t now)
{
    int c = sock_resolved(n->resolving, n->servers, MAX_SERVERS);
    if (c < 0)
        return;
    sock_resolve_drop(n->resolving);
    n->resolving = NULL;
    n->nservers = c;
    if (c)
        nlog(n, "directory: %d server%s", c, c == 1 ? "" : "s");
    else
        nlog(n, "directory: no server could be found");
    if (n->searching)
        n->search_start = now;      /* the wait for answers starts now */
    n->last_register = now - REGISTER_MS;
}

static void punch(sr2_net *n, const sock_addr *to)
{
    route r;
    int i;
    r.addr = *to;
    r.relayed = 0;
    for (i = 0; i < 3; i++)
        send_raw(n, &r, T_PUNCH, my_index_byte(n), NOBODY, 0, NULL, 0);
}

/* What the directory sends: the list, the other side's endpoint, no
 * such session, a relayed datagram. The token is checked by the caller. */
static void take_server(sr2_net *n, const sock_addr *from, uint8_t *pkt, int len, uint32_t now)
{
    route r;
    switch (pkt[4]) {
    case 'S': {
        int i, c = len > DHDR ? pkt[DHDR] : 0, pos = DHDR + 1;
        if (!n->searching)
            return;
        for (i = 0; i < c && pos + 16 + 6 + 68 <= len; i++, pos += 16 + 6 + 68) {
            const uint8_t *e = pkt + pos;
            int k, slot = -1;
            for (k = 0; k < n->nfound; k++)
                if (memcmp(n->found[k].guid, e, 16) == 0) {
                    slot = k;
                    break;
                }
            if (slot < 0) {
                if (n->nfound == SR2_MAX_SESSIONS)
                    break;
                slot = n->nfound++;
                n->found_via[slot] = *from;
            }
            memcpy(n->found[slot].guid, e, 16);
            memcpy(&n->found[slot].addr, e + 16, 4);
            n->found[slot].port = e[20] << 8 | e[21];
            n->found[slot].max_players = e[22];
            n->found[slot].players = e[23];
            n->found[slot].closed = e[24];
            memcpy(n->found[slot].name, e + 25, SR2_NAME_LEN);
            n->found[slot].name[SR2_NAME_LEN - 1] = 0;
            n->found[slot].version = e[25 + SR2_NAME_LEN];
            n->found_via[slot] = *from;
            n->found_at[slot] = now;
        }
        break;
    }
    case 'P':                           /* the host: open my NAT towards this guest */
        if (len >= DHDR + 6 && n->in_session && n->is_host) {
            sock_addr g;
            memcpy(&g.addr, pkt + DHDR, 4);
            g.port = pkt[DHDR + 4] << 8 | pkt[DHDR + 5];
            punch(n, &g);
        }
        break;
    case 'N':                           /* the guest: the directory has no such session; stop asking */
        if (n->joining && !n->peers[0].rt.relayed) {
            nlog(n, "the directory has no such session");
            n->join_refused = 1;
        }
        break;
    case 'C':                           /* the host: the cookie this server wants on a registration */
        if (len >= DHDR + 4 && n->in_session && n->is_host) {
            int i = server_index(n, from);
            if (i >= 0 && n->dcookie[i] != rd32(pkt + DHDR)) {
                n->dcookie[i] = rd32(pkt + DHDR);
                n->last_register = now - REGISTER_MS;   /* registered again at once, with it */
            }
        }
        break;
    case 'D':
        if (!n->in_session)
            return;
        r.relayed = 1;
        r.via = *from;
        if (n->is_host) {
            if (len < DHDR + 6)
                return;
            memcpy(&r.addr.addr, pkt + DHDR, 4);
            r.addr.port = pkt[DHDR + 4] << 8 | pkt[DHDR + 5];
            take_packet(n, &r, pkt + DHDR + 6, len - DHDR - 6, now);
        } else {
            r.addr = n->peers[0].rt.addr;
            take_packet(n, &r, pkt + DHDR, len - DHDR, now);
        }
        break;
    default:
        break;
    }
}

static void pump(sr2_net *n, uint32_t now)
{
    uint8_t pkt[DHDR + 6 + HDR + SR2_MAX_PAYLOAD + 64];
    route r;
    int len, guard = 256;
    if (n->resolving)
        take_resolved(n, now);
    while (guard-- && (len = sock_recv(n->sock, &r.addr, pkt, sizeof pkt)) >= 0) {
        if (len >= 4 && memcmp(pkt, DMAGIC, 4) == 0) {
            if (len >= DHDR && rd32(pkt + 5) == n->dtoken && server_index(n, &r.addr) >= 0)
                take_server(n, &r.addr, pkt, len, now);
            continue;
        }
        r.relayed = 0;
        take_packet(n, &r, pkt, len, now);
    }
}

/* The host's entry at the directory, refreshed every second, with the
 * cookie each server's challenge gave: a registration from a forged
 * address never sees its challenge, so it is never listed. */
static void register_session(sr2_net *n, uint32_t now)
{
    uint8_t buf[DHDR + 16 + 68 + 4];
    int i, len;
    if (n->kind != SR2_KIND_INTERNET || !n->is_host || n->lost || now - n->last_register < REGISTER_MS)
        return;
    n->last_register = now;
    dhead(n, buf, 'H');
    memcpy(buf + DHDR, n->guid, 16);
    len = DHDR + 16 + pack_record(n, buf + DHDR + 16);
    buf[len++] = SR2_PROTO;
    for (i = 0; i < n->nservers; i++) {
        wr32(buf + len, n->dcookie[i]);
        sock_send(n->sock, &n->servers[i], buf, len + 4);
    }
}

/* The host's entry taken down when it leaves. */
static void unregister_session(sr2_net *n)
{
    uint8_t buf[DHDR + 16];
    int i;
    if (n->kind != SR2_KIND_INTERNET || !n->is_host)
        return;
    dhead(n, buf, 'X');
    memcpy(buf + DHDR, n->guid, 16);
    for (i = 0; i < n->nservers; i++)
        sock_send(n->sock, &n->servers[i], buf, sizeof buf);
}

/* Resends, keep-alives, and the links that have died. */
static void timers(sr2_net *n, uint32_t now)
{
    int i;
    register_session(n, now);
    for (i = 0; i < SR2_MAX_PLAYERS; i++) {
        peer *p = &n->peers[i];
        uint32_t s;
        int dead = 0;
        if (!p->used)
            continue;
        for (s = p->send_seq - WINDOW + 1; s != p->send_seq + 1 && p->nunacked; s++) {
            rmsg *m = &p->unacked[s % WINDOW];
            if (!m->len || m->seq != s)
                continue;
            if (now - m->first > DEAD_MS)
                dead = 1;
            if (now - m->sent >= RESEND_MS) {
                wr32(m->data + 12, p->recv_seq);
                emit(n, &p->rt, m->data, m->len);
                m->sent = now;
                p->last_sent = now;
            }
        }
        if (now - p->last_heard > DEAD_MS)
            dead = 1;
        if (dead) {
            if (n->is_host)
                host_drop(n, p->index, "silent", now);
            else
                session_lost(n, "the host went silent");
            continue;
        }
        if (now - p->last_sent >= PING_MS)
            send_to(n, p, T_PING, NOBODY, NULL, 0, now);
    }
}

/* --- the API --- */

sr2_net *sr2_create(void)
{
    sr2_net *n = (sr2_net *)calloc(1, sizeof *n);
    if (!n)
        return NULL;
    sock_startup();
    n->sock = SOCK_INVALID;
    n->my_index = -1;
    sock_random((uint8_t *)&n->rnd, sizeof n->rnd);
    return n;
}

void sr2_destroy(sr2_net *n)
{
    if (!n)
        return;
    if (n->sock != SOCK_INVALID)
        sock_close(n->sock);
    sock_resolve_drop(n->resolving);
    free(n);
    sock_cleanup();
}

void sr2_set_log(sr2_net *n, void (*fn)(void *, const char *), void *ctx)
{
    n->log = fn;
    n->log_ctx = ctx;
}

int sr2_open(sr2_net *n, int kind, const char *address, uint32_t now)
{
    if (n->sock != SOCK_INVALID)
        sock_close(n->sock);
    n->sock = sock_open(SR2_PORT, &n->port);
    if (n->sock == SOCK_INVALID)
        return SR2_ERR;
    n->kind = kind;
    n->rnd ^= now ^ ((uint32_t)n->port << 16);
    sock_random((uint8_t *)&n->dtoken, sizeof n->dtoken);
    sock_random((uint8_t *)&n->secret, sizeof n->secret);
    n->have_target = 0;
    n->bad_target = 0;
    n->target.addr = htonl(INADDR_BROADCAST);
    n->target.port = SR2_PORT;
    n->nservers = 0;
    sock_resolve_drop(n->resolving);
    n->resolving = NULL;
    memset(n->dcookie, 0, sizeof n->dcookie);
    if (kind == SR2_KIND_DIRECT && address && address[0]) {
        /* the game opens the connection to host as well as to search, with
           whatever the address box holds; a bad one only matters to a search */
        if (sock_parse(address, SR2_PORT, &n->target) != 0) {
            nlog(n, "open: %s is not an address; a search will fail", address);
            n->bad_target = 1;
        } else
            n->have_target = 1;
    }
    if (kind == SR2_KIND_INTERNET) {
#ifdef SR2_TEST
        static const char *const defaults[] = {"localhost", NULL};   /* no real lookups under test */
#else
        static const char *const defaults[] = SR2_DIRECTORIES;
#endif
        const char *const one[] = {address};
        const char *const *names = address && address[0] ? one : defaults;   /* one server named, or the built-in list */
        int c = 0;
        while (names == defaults ? defaults[c] != NULL : c < 1)
            c++;
        /* the names are looked up off this thread: a resolver that is slow
           or absent would otherwise hold the game for as long as it takes
           to give up */
        n->resolving = sock_resolve(names, c, SR2_PORT + 1);
        if (!n->resolving) {
            nlog(n, "open: the directory lookup could not be started");
            return SR2_ERR;
        }
    }
    nlog(n, "open: kind %d, port %u, %s", kind, n->port, n->have_target ? address : "search");
    if (n->port != SR2_PORT)
        nlog(n, "open: port %u was taken; a LAN search will not find this machine", SR2_PORT);
    return SR2_OK;
}

int sr2_kind(const sr2_net *n) { return n->kind; }
uint16_t sr2_port(const sr2_net *n) { return n->port; }

void sr2_set_search(sr2_net *n, uint32_t addr, uint16_t port)
{
    if (!n->have_target) {
        n->target.addr = addr;
        n->target.port = port;
    }
}

void sr2_set_directory(sr2_net *n, uint32_t addr, uint16_t port)
{
    sock_resolve_drop(n->resolving);
    n->resolving = NULL;
    n->servers[0].addr = addr;
    n->servers[0].port = port;
    n->nservers = 1;
    memset(n->dcookie, 0, sizeof n->dcookie);
}

int sr2_enum(sr2_net *n, uint32_t now, sr2_session *out, int max)
{
    int i, c = 0;
    if (n->sock == SOCK_INVALID || n->bad_target)
        return SR2_ERR;
    if (!n->searching) {
        n->searching = 1;
        n->search_start = now;
        n->last_query = now - QUERY_MS;
        n->nfound = 0;
    }
    if (now - n->last_query >= QUERY_MS) {
        if (n->kind == SR2_KIND_INTERNET) {
            uint8_t buf[DHDR];
            dhead(n, buf, 'L');
            for (i = 0; i < n->nservers; i++)
                sock_send(n->sock, &n->servers[i], buf, sizeof buf);
        } else {
            route r;
            r.addr = n->target;
            r.relayed = 0;
            send_raw(n, &r, T_QUERY, NOBODY, NOBODY, 0, NULL, 0);
        }
        n->last_query = now;
    }
    pump(n, now);
    for (i = 0; i < n->nfound; i++) {       /* the ones not heard from lately go, so the table never fills with them */
        if (now - n->found_at[i] > SESSION_TTL_MS) {
            n->nfound--;
            if (i < n->nfound) {
                n->found[i] = n->found[n->nfound];
                n->found_at[i] = n->found_at[n->nfound];
                n->found_via[i] = n->found_via[n->nfound];
            }
            i--;
            continue;
        }
        if (c < max)
            out[c] = n->found[i];
        c++;
    }
    if (c == 0 && (n->resolving || now - n->search_start < ENUM_WAIT_MS))
        return SR2_CONNECTING;
    return c > max ? max : c;
}

static void session_reset(sr2_net *n)
{
    n->searching = 0;
    n->in_session = 0;
    n->is_host = 0;
    n->lost = 0;
    n->joining = n->join_refused = 0;
    n->announced = 0;
    n->my_index = -1;
    n->max_players = SR2_MAX_PLAYERS;
    n->open = 1;
    memset(n->players, 0, sizeof n->players);
    memset(n->reserved, 0, sizeof n->reserved);
    memset(n->peers, 0, sizeof n->peers);
    n->ev_head = n->ev_count = 0;
    n->q_head = n->q_count = 0;
}

int sr2_host(sr2_net *n, const char *name, int max_players, uint32_t now)
{
    int i;
    if (n->sock == SOCK_INVALID)
        return SR2_ERR;
    session_reset(n);
    n->in_session = 1;
    n->is_host = 1;
    n->max_players = max_players > 0 && max_players <= SR2_MAX_PLAYERS ? max_players : SR2_MAX_PLAYERS;
    copy_name(n->session_name, name);
    sock_random(n->guid, 16);
    for (i = 0; i < 16; i += 4)
        wr32(n->guid + i, rd32(n->guid + i) ^ rnd(n) ^ (now * 2654435761u));
    sock_random((uint8_t *)&n->secret, sizeof n->secret);
    n->query_tokens = QUERY_RATE;
    n->query_last = now;
    nlog(n, "hosting '%s' for %d", n->session_name, n->max_players);
    return SR2_OK;
}

static void send_join(sr2_net *n, uint32_t now)
{
    uint8_t buf[DHDR + 16 + JOIN_LEN];
    memcpy(buf, n->guid, 16);
    memcpy(buf + 16, n->join_nonce, 8);
    buf[24] = SR2_PROTO;
    wr32(buf + 25, n->join_cookie);
    send_raw(n, &n->peers[0].rt, T_JOIN, NOBODY, NOBODY, 0, buf, JOIN_LEN);
    if (n->kind == SR2_KIND_INTERNET && !n->peers[0].rt.relayed) {
        dhead(n, buf, 'J');
        memcpy(buf + DHDR, n->guid, 16);
        sock_send(n->sock, &n->relay, buf, DHDR + 16);
    }
    n->join_last = now;
}

int sr2_join(sr2_net *n, const sr2_session *s, uint32_t now)
{
    route host;
    int i;
    if (n->sock == SOCK_INVALID)
        return SR2_ERR;
    if (s->version < SR2_PROTO_MIN) {
        nlog(n, "'%s' is hosted from before the wire's version (%d): not joined", s->name, s->version);
        return SR2_REFUSED;
    }
    session_reset(n);
    host.addr.addr = s->addr;
    host.addr.port = s->port;
    host.relayed = 0;
    n->relay = n->servers[0];
    for (i = 0; i < n->nfound; i++)
        if (memcmp(n->found[i].guid, s->guid, 16) == 0 && n->found_via[i].port)
            n->relay = n->found_via[i];
    sock_random(n->join_nonce, 8);
    n->join_cookie = 0;
    n->in_session = 1;
    n->joining = 1;
    n->join_start = now;
    n->join_last = now;
    memcpy(n->guid, s->guid, 16);
    copy_name(n->session_name, s->name);
    n->max_players = s->max_players > SR2_MAX_PLAYERS ? SR2_MAX_PLAYERS : s->max_players;
    peer_reset(&n->peers[0], &host, -1, now);
    nlog(n, "joining '%s' at %08x:%u", s->name, ntohl(host.addr.addr), host.addr.port);
    send_join(n, now);
    return SR2_CONNECTING;
}

int sr2_join_status(sr2_net *n, uint32_t now)
{
    if (!n->in_session || n->is_host)
        return SR2_ERR;
    if (!n->joining)
        return n->my_index >= 0 ? SR2_OK : SR2_ERR;
    pump(n, now);
    if (n->join_refused) {
        session_reset(n);
        return SR2_REFUSED;
    }
    if (n->my_index >= 0) {
        n->joining = 0;
        nlog(n, "joined as %d", n->my_index);
        return SR2_OK;
    }
    if (n->kind == SR2_KIND_INTERNET && !n->peers[0].rt.relayed && now - n->join_start > PUNCH_MS) {
        nlog(n, "no direct road: through the relay");
        n->peers[0].rt.relayed = 1;
        n->peers[0].rt.via = n->relay;
        n->join_start = now;
    }
    if (now - n->join_start > JOIN_WAIT_MS) {
        nlog(n, "no answer from the host");
        session_reset(n);
        return SR2_ERR;
    }
    if (now - n->join_last >= JOIN_RETRY_MS)
        send_join(n, now);
    return SR2_CONNECTING;
}

void sr2_leave(sr2_net *n, uint32_t now)
{
    int i;
    if (!n->in_session)
        return;
    if (!n->lost)
        for (i = 0; i < SR2_MAX_PLAYERS; i++)
            if (n->peers[i].used) {
                send_to(n, &n->peers[i], T_LEAVE, NOBODY, NULL, 0, now);
                send_to(n, &n->peers[i], T_LEAVE, NOBODY, NULL, 0, now);
            }
    unregister_session(n);
    nlog(n, "left");
    session_reset(n);
}

int sr2_in_session(const sr2_net *n) { return n->in_session && !n->lost; }
int sr2_is_host(const sr2_net *n) { return n->in_session && n->is_host; }
int sr2_my_index(const sr2_net *n) { return n->my_index; }

int sr2_player_create(sr2_net *n, const char *name, uint32_t now)
{
    int idx, i;
    if (!n->in_session || n->lost)
        return SR2_ERR;
    if (n->is_host) {
        idx = free_index(n);
        if (idx < 0)
            return SR2_ERR;
        n->my_index = idx;
        n->players[idx].used = 1;
        n->players[idx].host = 1;
        n->players[idx].local = 1;
        copy_name(n->players[idx].name, name);
        n->announced = 1;
        push_event(n, SR2_EV_HOST, idx);
        push_event(n, SR2_EV_CREATED, idx);
        host_send_roster(n, now);
        return idx;
    }
    idx = n->my_index;
    if (idx < 0 || !n->players[idx].used)
        return SR2_ERR;
    copy_name(n->players[idx].name, name);
    n->players[idx].local = 1;
    n->announced = 1;
    /* the events the join's roster earned: the host first, then everyone */
    push_event(n, SR2_EV_HOST, n->peers[0].index);
    for (i = 0; i < SR2_MAX_PLAYERS; i++)
        if (n->players[i].used)
            push_event(n, SR2_EV_CREATED, i);
    send_reliable(n, &n->peers[0], T_NAME, idx, NOBODY, n->players[idx].name, SR2_NAME_LEN, now);
    return idx;
}

void sr2_set_open(sr2_net *n, int open, uint32_t now)
{
    (void)now;
    if (n->is_host)
        n->open = open != 0;
}

int sr2_session_info(const sr2_net *n, sr2_session *out)
{
    if (!n->in_session)
        return SR2_ERR;
    memset(out, 0, sizeof *out);
    memcpy(out->guid, n->guid, 16);
    out->max_players = n->max_players;
    out->players = count_players(n);
    out->closed = !n->open;
    out->version = SR2_PROTO;
    copy_name(out->name, n->session_name);
    return SR2_OK;
}

int sr2_player_count(const sr2_net *n, int *max, int *current)
{
    if (!n->in_session)
        return SR2_ERR;
    *max = n->max_players;
    *current = count_players(n);
    return SR2_OK;
}

int sr2_player_info(const sr2_net *n, int index, sr2_player *out)
{
    if (!n->in_session || index < 0 || index >= SR2_MAX_PLAYERS || !n->players[index].used)
        return SR2_ERR;
    out->index = index;
    out->host = n->players[index].host;
    out->local = n->players[index].local;
    copy_name(out->name, n->players[index].name);
    return SR2_OK;
}

int sr2_slot_reserved(const sr2_net *n, int index)
{
    return index >= 0 && index < SR2_MAX_PLAYERS && n->reserved[index];
}

int sr2_slot_reserve(sr2_net *n, int index, int on, uint32_t now)
{
    if (!n->is_host || index < 0 || index >= SR2_MAX_PLAYERS)
        return SR2_ERR;
    if (n->reserved[index] == (on != 0))
        return SR2_NONE;
    n->reserved[index] = on != 0;
    if (on && n->players[index].used && !n->players[index].local)
        host_drop(n, index, "slot closed", now);
    host_broadcast_reliable(n, T_SLOTS, n->reserved, SR2_MAX_PLAYERS, now);
    return SR2_OK;
}

int sr2_poll(sr2_net *n, uint32_t now)
{
    if (n->sock == SOCK_INVALID)
        return SR2_ERR;
    pump(n, now);
    if (n->in_session && !n->lost)
        timers(n, now);
    return n->in_session && n->lost ? SR2_ERR : SR2_OK;
}

int sr2_send(sr2_net *n, int to, const void *data, int len, int reliable, uint32_t now)
{
    int i, dest = to < 0 ? NOBODY : to;
    if (!n->in_session || n->lost || n->my_index < 0 || len > SR2_MAX_PAYLOAD)
        return SR2_ERR;
    if (reliable) {                     /* a full window: the acks may be waiting in the socket */
        for (i = 0; i < SR2_MAX_PLAYERS; i++)
            if (n->peers[i].used && n->peers[i].nunacked == WINDOW) {
                pump(n, now);
                break;
            }
    }
    if (n->is_host) {
        int r = SR2_OK;
        for (i = 0; i < SR2_MAX_PLAYERS; i++) {
            peer *p = &n->peers[i];
            if (!p->used || p->index < 0 || (to >= 0 && p->index != to))
                continue;
            if (reliable) {
                if (send_reliable(n, p, T_GAME, n->my_index, dest, data, len, now) != SR2_OK)
                    r = SR2_ERR;
            } else
                send_to(n, p, T_GAME, dest, data, len, now);
        }
        return r;
    }
    if (reliable)
        return send_reliable(n, &n->peers[0], T_GAME, n->my_index, dest, data, len, now);
    send_to(n, &n->peers[0], T_GAME, dest, data, len, now);
    return SR2_OK;
}

const char *sr2_status(sr2_net *n)
{
    uint32_t addrs[3];
    int i, c = sock_local(addrs, 3), pos = 0;
    n->status[0] = 0;
    for (i = 0; i < c; i++) {
        const uint8_t *b = (const uint8_t *)&addrs[i];
        pos += snprintf(n->status + pos, sizeof n->status - pos, "%s%u.%u.%u.%u:%u",
                        i ? " , " : "IP Address : ", b[0], b[1], b[2], b[3], n->port);
        if (pos >= (int)sizeof n->status)
            break;
    }
    return n->status;
}

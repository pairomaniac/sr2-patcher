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
#define DEAD_MS         6000
#define QUERY_MS        400
#define SESSION_TTL_MS  3000
#define ENUM_WAIT_MS    3000
#define JOIN_WAIT_MS    5000
#define JOIN_RETRY_MS   300
#define PUNCH_MS        4000    /* direct tries before the relay */
#define REGISTER_MS     1000    /* a host's refresh at the directory */
#define MAX_SERVERS     4
#define DMAGIC          "SR2D"

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
    T_PUNCH             /* opens a NAT; ignored */
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
    uint32_t  nonce;                /* the join's, so a second route to one guest is one guest */
    int       index;                /* the player at the other end, -1 until known */
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
    sock_addr servers[MAX_SERVERS]; /* the directory, SR2_KIND_INTERNET */
    int       nservers;
    uint32_t  last_register;
    sock_addr relay;                /* the server the join went through */
    uint32_t  join_nonce;
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
    uint8_t wrap[5 + 16 + 6 + HDR + SR2_MAX_PAYLOAD];
    int pos;
    if (!to->relayed) {
        sock_send(n->sock, &to->addr, data, len);
        return;
    }
    memcpy(wrap, DMAGIC "R", 5);
    memcpy(wrap + 5, n->guid, 16);
    pos = 21;
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
        nlog(n, "link %d: window full, a %d-byte message lost", p->index, len);
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

/* T_SESSION: max, players, closed, guid[16], name[64]. */
static int pack_session(const sr2_net *n, uint8_t *out)
{
    out[0] = n->max_players;
    out[1] = count_players(n);
    out[2] = !n->open || free_index(n) < 0;
    memcpy(out + 3, n->guid, 16);
    memcpy(out + 19, n->session_name, SR2_NAME_LEN);
    return 19 + SR2_NAME_LEN;
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
    for (i = 0; i < WINDOW && p->nunacked; i++) {
        rmsg *m = &p->unacked[i];
        if (m->len && (int32_t)(m->seq - ack) <= 0) {
            m->len = 0;
            p->nunacked--;
        }
    }
}

/* A reliable packet in: in order, held for later, or a duplicate. */
static void take_reliable(sr2_net *n, peer *p, const uint8_t *pkt, int len, uint32_t now)
{
    uint32_t seq = rd32(pkt + 8);
    int32_t ahead = (int32_t)(seq - p->recv_seq);
    if (ahead <= 0) {
        /* seen already; the ack below says so again */
    } else if (ahead == 1) {
        p->recv_seq = seq;
        handle_message(n, p, pkt, len, now);
        for (;;) {
            rmsg *h = &p->held[(p->recv_seq + 1) % WINDOW];
            if (!h->len || h->seq != p->recv_seq + 1)
                break;
            int hlen = h->len;
            p->recv_seq++;
            h->len = 0;
            handle_message(n, p, h->data, hlen, now);
        }
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
    uint8_t buf[2 + SR2_MAX_PLAYERS + 1 + SR2_MAX_PLAYERS * (2 + SR2_NAME_LEN)];
    int idx, blen, i;
    uint8_t reason;
    uint32_t nonce;
    if (len < HDR + 20 || memcmp(pkt + HDR, n->guid, 16) != 0) {
        reason = 1;                     /* not this session */
        send_raw(n, from, T_REFUSE, my_index_byte(n), NOBODY, 0, &reason, 1);
        return;
    }
    nonce = rd32(pkt + HDR + 16);
    if (!p)                             /* the same guest by another road: a NAT gave it another address, or a direct join reached a relayed one */
        for (i = 0; i < SR2_MAX_PLAYERS; i++)
            if (n->peers[i].used && n->peers[i].nonce == nonce) {
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
        p->nonce = nonce;
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
            } else if (dest < SR2_MAX_PLAYERS && n->peers[dest].used && n->peers[dest].index >= 0) {
                if (pkt[5] & F_RELIABLE)
                    send_reliable(n, &n->peers[dest], T_GAME, from, dest, body, blen, now);
                else
                    send_raw(n, &n->peers[dest].rt, T_GAME, from, dest, n->peers[dest].recv_seq, body, blen);
            }
        } else {
            queue_game(n, pkt[6], body, blen);
        }
        break;
    case T_WELCOME:
        if (n->is_host || blen < 2 + SR2_MAX_PLAYERS + 1 || body[0] >= SR2_MAX_PLAYERS || body[1] >= SR2_MAX_PLAYERS)
            break;                      /* an index past the table is no seat, the host's included */
        n->my_index = body[0];
        p->index = body[1];
        memcpy(n->reserved, body + 2, SR2_MAX_PLAYERS);
        take_roster(n, body + 2 + SR2_MAX_PLAYERS, blen - 2 - SR2_MAX_PLAYERS);
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
            uint8_t buf[19 + SR2_NAME_LEN];
            int blen = pack_session(n, buf);
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
            nlog(n, "refused: reason %d", pkt[HDR]);
            n->join_refused = 1;
        }
        return;
    }
    if (pkt[5] & F_RELIABLE)
        take_reliable(n, p, pkt, len, now);
    else
        handle_message(n, p, pkt, len, now);
}

static int is_server(const sr2_net *n, const sock_addr *a)
{
    int i;
    for (i = 0; i < n->nservers; i++)
        if (sock_addr_eq(&n->servers[i], a))
            return 1;
    return 0;
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

/* What the directory sends: the list, the other side's endpoint, a
 * relayed datagram. */
static void take_server(sr2_net *n, const sock_addr *from, uint8_t *pkt, int len, uint32_t now)
{
    route r;
    switch (pkt[4]) {
    case 'S': {
        int i, c = len > 5 ? pkt[5] : 0, pos = 6;
        if (!n->searching)
            return;
        for (i = 0; i < c && pos + 16 + 6 + 67 <= len; i++, pos += 16 + 6 + 67) {
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
            n->found_at[slot] = now;
        }
        break;
    }
    case 'P':                           /* the host: open my NAT towards this guest */
        if (len >= 11 && n->in_session && n->is_host) {
            sock_addr g;
            memcpy(&g.addr, pkt + 5, 4);
            g.port = pkt[9] << 8 | pkt[10];
            punch(n, &g);
        }
        break;
    case 'D':
        if (!n->in_session)
            return;
        r.relayed = 1;
        r.via = *from;
        if (n->is_host) {
            if (len < 11)
                return;
            memcpy(&r.addr.addr, pkt + 5, 4);
            r.addr.port = pkt[9] << 8 | pkt[10];
            take_packet(n, &r, pkt + 11, len - 11, now);
        } else {
            r.addr = n->peers[0].rt.addr;
            take_packet(n, &r, pkt + 5, len - 5, now);
        }
        break;
    default:
        break;
    }
}

static void pump(sr2_net *n, uint32_t now)
{
    uint8_t pkt[5 + 6 + HDR + SR2_MAX_PAYLOAD + 64];
    route r;
    int len, guard = 256;
    while (guard-- && (len = sock_recv(n->sock, &r.addr, pkt, sizeof pkt)) >= 0) {
        if (len >= 5 && memcmp(pkt, DMAGIC, 4) == 0) {
            if (is_server(n, &r.addr))
                take_server(n, &r.addr, pkt, len, now);
            continue;
        }
        r.relayed = 0;
        take_packet(n, &r, pkt, len, now);
    }
}

/* The host's entry at the directory, refreshed every second. */
static void register_session(sr2_net *n, uint32_t now)
{
    uint8_t buf[5 + 16 + 67];
    int i;
    if (n->kind != SR2_KIND_INTERNET || !n->is_host || n->lost || now - n->last_register < REGISTER_MS)
        return;
    n->last_register = now;
    memcpy(buf, DMAGIC "H", 5);
    memcpy(buf + 5, n->guid, 16);
    pack_record(n, buf + 21);
    for (i = 0; i < n->nservers; i++)
        sock_send(n->sock, &n->servers[i], buf, 5 + 16 + 3 + SR2_NAME_LEN);
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
    return n;
}

void sr2_destroy(sr2_net *n)
{
    if (!n)
        return;
    if (n->sock != SOCK_INVALID)
        sock_close(n->sock);
    free(n);
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
    n->have_target = 0;
    n->target.addr = htonl(INADDR_BROADCAST);
    n->target.port = SR2_PORT;
    n->nservers = 0;
    if (kind == SR2_KIND_DIRECT && address && address[0]) {
        if (sock_parse(address, SR2_PORT, &n->target) != 0) {
            nlog(n, "open: %s is not an address", address);
            return SR2_ERR;
        }
        n->have_target = 1;
    }
    if (kind == SR2_KIND_INTERNET) {
        static const char *const defaults[] = SR2_DIRECTORIES;
        int i;
        if (address && address[0]) {
            if (sock_parse(address, SR2_PORT + 1, &n->servers[0]) == 0)
                n->nservers = 1;
        } else {
            for (i = 0; defaults[i] && n->nservers < MAX_SERVERS; i++)
                if (sock_parse(defaults[i], SR2_PORT + 1, &n->servers[n->nservers]) == 0)
                    n->nservers++;
        }
        if (!n->nservers) {
            nlog(n, "open: no directory server could be found");
            return SR2_ERR;
        }
    }
    nlog(n, "open: kind %d, port %u, %s", kind, n->port, n->have_target ? address : "search");
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
    n->servers[0].addr = addr;
    n->servers[0].port = port;
    n->nservers = 1;
}

int sr2_enum(sr2_net *n, uint32_t now, sr2_session *out, int max)
{
    int i, c = 0;
    if (n->sock == SOCK_INVALID)
        return SR2_ERR;
    if (!n->searching) {
        n->searching = 1;
        n->search_start = now;
        n->last_query = now - QUERY_MS;
        n->nfound = 0;
    }
    if (now - n->last_query >= QUERY_MS) {
        if (n->kind == SR2_KIND_INTERNET) {
            for (i = 0; i < n->nservers; i++)
                sock_send(n->sock, &n->servers[i], DMAGIC "L", 5);
        } else {
            route r;
            r.addr = n->target;
            r.relayed = 0;
            send_raw(n, &r, T_QUERY, NOBODY, NOBODY, 0, NULL, 0);
        }
        n->last_query = now;
    }
    pump(n, now);
    for (i = 0; i < n->nfound; i++) {
        if (now - n->found_at[i] > SESSION_TTL_MS)
            continue;
        if (c < max)
            out[c] = n->found[i];
        c++;
    }
    if (c == 0 && now - n->search_start < ENUM_WAIT_MS)
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
    for (i = 0; i < 16; i += 4)
        wr32(n->guid + i, rnd(n) ^ (now * 2654435761u));
    nlog(n, "hosting '%s' for %d", n->session_name, n->max_players);
    return SR2_OK;
}

static void send_join(sr2_net *n, uint32_t now)
{
    uint8_t buf[20 + 16 + 5];
    memcpy(buf, n->guid, 16);
    wr32(buf + 16, n->join_nonce);
    send_raw(n, &n->peers[0].rt, T_JOIN, NOBODY, NOBODY, 0, buf, 20);
    if (n->kind == SR2_KIND_INTERNET && !n->peers[0].rt.relayed) {
        memcpy(buf, DMAGIC "J", 5);
        memcpy(buf + 5, n->guid, 16);
        sock_send(n->sock, &n->relay, buf, 21);
    }
    n->join_last = now;
}

int sr2_join(sr2_net *n, const sr2_session *s, uint32_t now)
{
    route host;
    int i;
    if (n->sock == SOCK_INVALID)
        return SR2_ERR;
    session_reset(n);
    host.addr.addr = s->addr;
    host.addr.port = s->port;
    host.relayed = 0;
    n->relay = n->servers[0];
    for (i = 0; i < n->nfound; i++)
        if (memcmp(n->found[i].guid, s->guid, 16) == 0)
            n->relay = n->found_via[i];
    n->join_nonce = rnd(n) ^ now;
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
    if (n->is_host) {
        for (i = 0; i < SR2_MAX_PLAYERS; i++) {
            peer *p = &n->peers[i];
            if (!p->used || p->index < 0 || (to >= 0 && p->index != to))
                continue;
            if (reliable)
                send_reliable(n, p, T_GAME, n->my_index, dest, data, len, now);
            else
                send_to(n, p, T_GAME, dest, data, len, now);
        }
        return SR2_OK;
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

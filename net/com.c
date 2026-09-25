/*
 * com.c - the replacement MGNetWk.dll: the stock DLL's three COM objects
 * over sr2net.c.
 *
 * Same CLSID, same interface ids, same vtable slots and calling
 * convention as the Musashi original (docs/NETWORK.md has the map), so
 * the exe and its manifest are none the wiser. Slots the exe never calls
 * return E_NOTIMPL. Player ids are index + 1, so none is 0.
 *
 * Log = 1 under [Network] in SR2.CFG beside the exe turns logging on,
 * to logs\sr2-net.log: what the core did, one line each. Staging = 1
 * there sends INTERNET to the staging directory.
 */
#include <winsock2.h>
#include <windows.h>
#include <stdio.h>
#include <string.h>

#include "sr2net.h"

#define DPERR_ACCESSDENIED    0x88770005
#define DPERR_BUFFERTOOSMALL  0x8877001e
#define DPERR_NOMESSAGES      0x887700be
#define DPERR_NOSESSIONS      0x8877012e
#define DPERR_SESSIONLOST     0x88770136
#define DPERR_CONNECTING      0x8877015e

#define RECORD_SIZE   0x60
#define LATENCY_MS    1500      /* what GetCaps reports: the exe's search window after the first answer */

static const GUID IID_Unknown  = {0x00000000, 0x0000, 0x0000, {0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46}};
static const GUID IID_Factory  = {0x00000001, 0x0000, 0x0000, {0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46}};
static const GUID CLSID_MGNetWk = {0x0D5837F0, 0x3E3C, 0x11D2, {0x92, 0x4E, 0x00, 0xA0, 0xC9, 0x69, 0x7E, 0x45}};
static const GUID IID_Network  = {0x0D5837F1, 0x3E3C, 0x11D2, {0x92, 0x4E, 0x00, 0xA0, 0xC9, 0x69, 0x7E, 0x45}};
static const GUID IID_Session  = {0x0D5837F2, 0x3E3C, 0x11D2, {0x92, 0x4E, 0x00, 0xA0, 0xC9, 0x69, 0x7E, 0x45}};
static const GUID IID_Player   = {0x0D5837F3, 0x3E3C, 0x11D2, {0x92, 0x4E, 0x00, 0xA0, 0xC9, 0x69, 0x7E, 0x45}};

static HINSTANCE g_module;
static LONG g_objects;
static FILE *g_log;

static void log_line(void *ctx, const char *line)
{
    (void)ctx;
    if (g_log) {
        fprintf(g_log, "%lu %s\n", (unsigned long)GetTickCount(), line);
        fflush(g_log);
    }
}

/* The path of a file beside the exe, or 0 when it does not fit. */
static int beside_exe(const char *name, char *path, size_t size)
{
    DWORD n = GetModuleFileNameA(NULL, path, (DWORD)size);
    if (n == 0 || n >= size)
        return 0;
    while (n && path[n - 1] != '\\')
        n--;
    if (n + strlen(name) + 1 > size)
        return 0;
    strcpy(path + n, name);
    return 1;
}

/* A [Network] setting in SR2.CFG beside the exe: Log = 1 writes
 * logs\sr2-net.log, Staging = 1 sends INTERNET to the staging directory. */
static int network_setting(const char *key)
{
    char path[MAX_PATH];
    if (!beside_exe("SR2.CFG", path, sizeof path))
        return 0;
    return GetPrivateProfileIntA("Network", key, 0, path) != 0;
}

static void log_open(void)
{
    char path[MAX_PATH];
    if (g_log || !network_setting("Log") || !beside_exe("logs", path, sizeof path))
        return;
    CreateDirectoryA(path, NULL);                   /* logs\, where the other diagnostics write */
    if (beside_exe("logs\\sr2-net.log", path, sizeof path))
        g_log = fopen(path, "a");
}

static int guid_eq(const GUID *a, const GUID *b) { return memcmp(a, b, sizeof(GUID)) == 0; }

/* ------------------------------------------------------------------ */
/* the objects                                                         */

typedef struct network network;
typedef struct session session;
typedef struct player  player;

struct network {
    const void *vtbl;
    LONG        refs;
    sr2_net    *net;
    GUID        app;
    sr2_session found[SR2_MAX_SESSIONS];
    int         nfound;
};

struct session {
    const void *vtbl;
    LONG        refs;
    network    *owner;
};

struct player {
    const void *vtbl;
    LONG        refs;
    session    *owner;
    int         index;
    int         local;
    char        name[SR2_NAME_LEN];
};

static uint32_t now_ms(void) { return GetTickCount(); }

/* the 0x60-byte session record the exe passes around */
static void put_session_record(const sr2_session *s, BYTE *rec)
{
    memset(rec, 0, RECORD_SIZE);
    *(DWORD *)(rec + 0) = RECORD_SIZE;
    *(DWORD *)(rec + 4) = s->max_players;
    *(DWORD *)(rec + 8) = s->players;
    *(DWORD *)(rec + 0xc) = s->closed;
    memcpy(rec + 0x10, s->guid, 16);
    memcpy(rec + 0x20, s->name, SR2_NAME_LEN);
    rec[0x5f] = 0;
}

/* the 0x60-byte player record */
static void put_player_record(const sr2_player *p, BYTE *rec)
{
    memset(rec, 0, RECORD_SIZE);
    *(DWORD *)(rec + 0) = RECORD_SIZE;
    *(DWORD *)(rec + 4) = p->index + 1;
    *(DWORD *)(rec + 8) = p->index;
    *(DWORD *)(rec + 0x10) = (p->host ? 1 : 0) | (p->local ? 2 : 0);
    memcpy(rec + 0x20, p->name, SR2_NAME_LEN);
    rec[0x5f] = 0;
}

/* ------------------------------------------------------------------ */
/* player                                                              */

static HRESULT __stdcall Player_QueryInterface(player *p, const GUID *riid, void **out)
{
    if (guid_eq(riid, &IID_Player) || guid_eq(riid, &IID_Unknown)) {
        *out = p;
        InterlockedIncrement(&p->refs);
        return S_OK;
    }
    *out = NULL;
    return E_NOINTERFACE;
}

static ULONG __stdcall Player_AddRef(player *p) { return InterlockedIncrement(&p->refs); }

static ULONG __stdcall Session_Release(session *s);

static ULONG __stdcall Player_Release(player *p)
{
    LONG r = InterlockedDecrement(&p->refs);
    if (r == 0) {
        Session_Release(p->owner);
        HeapFree(GetProcessHeap(), 0, p);
        InterlockedDecrement(&g_objects);
    }
    return r;
}

static HRESULT __stdcall Player_NotImpl(player *p) { (void)p; return E_NOTIMPL; }

static int player_fetch(player *p, sr2_player *info)
{
    return sr2_player_info(p->owner->owner->net, p->index, info) == SR2_OK;
}

static HRESULT __stdcall Player_GetName(player *p, char **name)
{
    sr2_player info;
    if (!name)
        return E_INVALIDARG;
    if (player_fetch(p, &info))
        memcpy(p->name, info.name, SR2_NAME_LEN);
    *name = p->name;
    return S_OK;
}

static HRESULT __stdcall Player_GetInfo(player *p, BYTE *rec)
{
    sr2_player info;
    if (!rec)
        return E_INVALIDARG;
    if (!player_fetch(p, &info)) {
        memset(&info, 0, sizeof info);
        info.index = -1;
        info.local = p->local;
    }
    put_player_record(&info, rec);
    return S_OK;
}

static HRESULT __stdcall Player_SetInfo(player *p, const BYTE *rec) { (void)p; (void)rec; return S_OK; }

static HRESULT __stdcall Player_GetFlags(player *p, DWORD *flags)
{
    sr2_player info;
    if (!flags)
        return E_INVALIDARG;
    *flags = 0;
    if (player_fetch(p, &info))
        *flags = (info.host ? 1 : 0) | (info.local ? 2 : 0);
    return S_OK;
}

static HRESULT __stdcall Player_SendTo(player *p, player *target, const void *data, DWORD len, BOOL guaranteed)
{
    int to = target ? target->index : -1;
    if (!data || len > SR2_MAX_PAYLOAD)
        return E_INVALIDARG;
    return sr2_send(p->owner->owner->net, to, data, (int)len, guaranteed != 0, now_ms()) == SR2_OK ? S_OK : E_FAIL;
}

static HRESULT __stdcall Player_PopUnsequenced(player *p, DWORD *tag, void *buf, DWORD *len)
{
    int from = 0, n, r;
    if (!len)
        return E_INVALIDARG;
    n = (int)*len;
    r = sr2_recv(p->owner->owner->net, &from, buf, &n);
    if (r == SR2_NONE) {
        *len = 0;
        return DPERR_NOMESSAGES;
    }
    if (r == SR2_TOOSMALL) {
        *len = n;
        return DPERR_BUFFERTOOSMALL;
    }
    *len = n;
    if (tag)
        *tag = from;
    return S_OK;
}

static const void *player_vtbl[16] = {
    Player_QueryInterface, Player_AddRef, Player_Release,
    Player_NotImpl,                 /* +0x0c Init */
    Player_NotImpl,                 /* +0x10 SetName */
    Player_GetName,                 /* +0x14 */
    Player_GetInfo,                 /* +0x18 */
    Player_SetInfo,                 /* +0x1c */
    Player_GetFlags,                /* +0x20 */
    Player_NotImpl,                 /* +0x24 GetIdent */
    Player_SendTo,                  /* +0x28 */
    Player_PopUnsequenced,          /* +0x2c */
    Player_NotImpl,                 /* +0x30 SendSequenced */
    Player_NotImpl,                 /* +0x34 ReadCurrent */
    Player_NotImpl,                 /* +0x38 GetQueue */
    Player_NotImpl,                 /* +0x3c dtor */
};

static ULONG __stdcall Session_AddRef(session *s);

static player *player_new(session *s, int index, int local)
{
    player *p = (player *)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, sizeof *p);
    if (!p)
        return NULL;
    p->vtbl = player_vtbl;
    p->refs = 1;
    p->owner = s;
    Session_AddRef(s);
    p->index = index;
    p->local = local;
    InterlockedIncrement(&g_objects);
    return p;
}

/* ------------------------------------------------------------------ */
/* session                                                             */

static HRESULT __stdcall Session_QueryInterface(session *s, const GUID *riid, void **out)
{
    if (guid_eq(riid, &IID_Session) || guid_eq(riid, &IID_Unknown)) {
        *out = s;
        InterlockedIncrement(&s->refs);
        return S_OK;
    }
    *out = NULL;
    return E_NOINTERFACE;
}

static ULONG __stdcall Session_AddRef(session *s) { return InterlockedIncrement(&s->refs); }

static ULONG __stdcall Network_Release(network *n);

static ULONG __stdcall Session_Release(session *s)
{
    LONG r = InterlockedDecrement(&s->refs);
    if (r == 0) {
        sr2_leave(s->owner->net, now_ms());
        Network_Release(s->owner);
        HeapFree(GetProcessHeap(), 0, s);
        InterlockedDecrement(&g_objects);
    }
    return r;
}

static HRESULT __stdcall Session_NotImpl(session *s) { (void)s; return E_NOTIMPL; }

static HRESULT __stdcall Session_GetInfo(session *s, BYTE *rec)
{
    sr2_session info;
    if (!rec || *(DWORD *)rec < RECORD_SIZE)
        return DPERR_BUFFERTOOSMALL;
    if (sr2_session_info(s->owner->net, &info) != SR2_OK)
        return E_FAIL;
    put_session_record(&info, rec);
    return S_OK;
}

static HRESULT __stdcall Session_SetOpen(session *s, BOOL open)
{
    sr2_set_open(s->owner->net, open != 0, now_ms());
    return S_OK;
}

static HRESULT __stdcall Session_CreatePlayer(session *s, const char *name, player **out)
{
    int idx;
    if (!name || !out)
        return E_INVALIDARG;
    idx = sr2_player_create(s->owner->net, name, now_ms());
    if (idx < 0)
        return E_FAIL;
    *out = player_new(s, idx, 1);
    return *out ? S_OK : E_OUTOFMEMORY;
}

/* An index with nobody in it still gets an object, its name empty and
 * its record index -1: the team room's row draw (0x4358ce) writes the
 * name pointer only where the call succeeded and reads it either way,
 * so a failure here leaves it whatever the stack held - a crash on
 * entering the room, on the machines where that word is not benign.
 * Only an index outside the table is refused. */
static HRESULT __stdcall Session_FindPlayerByIndex(session *s, DWORD index, player **out)
{
    sr2_player info;
    int local = 0;
    if (!out)
        return E_INVALIDARG;
    if ((int)index < 0 || (int)index >= SR2_MAX_PLAYERS)
        return E_FAIL;
    if (sr2_player_info(s->owner->net, (int)index, &info) == SR2_OK)
        local = info.local;
    *out = player_new(s, (int)index, local);
    return *out ? S_OK : E_OUTOFMEMORY;
}

static HRESULT __stdcall Session_GetPlayerCounts(session *s, DWORD *max, DWORD *current)
{
    int m = 0, c = 0;
    if (sr2_player_count(s->owner->net, &m, &c) != SR2_OK)
        return E_FAIL;
    if (max)
        *max = m;
    if (current)
        *current = c;
    return S_OK;
}

static HRESULT __stdcall Session_Poll(session *s)
{
    return sr2_poll(s->owner->net, now_ms()) == SR2_OK ? S_OK : DPERR_SESSIONLOST;
}

static HRESULT __stdcall Session_PopEvent(session *s, DWORD *evt)
{
    sr2_event ev;
    if (!evt)
        return E_INVALIDARG;
    if (sr2_pop_event(s->owner->net, &ev) != SR2_OK)
        return 1;
    evt[0] = ev.type;
    evt[1] = ev.type == SR2_EV_LOST ? 0 : ev.a + 1;
    evt[2] = ev.type == SR2_EV_LOST ? 0 : ev.a;
    evt[3] = 0;
    return S_OK;
}

static HRESULT __stdcall Session_IsSlotReserved(session *s, DWORD index, DWORD *out)
{
    if (!out)
        return E_INVALIDARG;
    *out = sr2_slot_reserved(s->owner->net, (int)index) ? 1 : 0;
    return S_OK;
}

static HRESULT __stdcall Session_SetSlotReserved(session *s, DWORD index, BOOL on)
{
    int r = sr2_slot_reserve(s->owner->net, (int)index, on != 0, now_ms());
    return r == SR2_OK ? S_OK : S_FALSE;
}

static const void *session_vtbl[17] = {
    Session_QueryInterface, Session_AddRef, Session_Release,
    Session_NotImpl,                /* +0x0c Init */
    Session_GetInfo,                /* +0x10 */
    Session_SetOpen,                /* +0x14 */
    Session_CreatePlayer,           /* +0x18 */
    Session_NotImpl,                /* +0x1c DestroyPlayer */
    Session_NotImpl,                /* +0x20 GetPlayerByListPos */
    Session_FindPlayerByIndex,      /* +0x24 */
    Session_GetPlayerCounts,        /* +0x28 */
    Session_Poll,                   /* +0x2c */
    Session_PopEvent,               /* +0x30 */
    Session_NotImpl,                /* +0x34 SetReady */
    Session_IsSlotReserved,         /* +0x38 */
    Session_SetSlotReserved,        /* +0x3c */
    Session_NotImpl,                /* +0x40 dtor */
};

static ULONG __stdcall Network_AddRef(network *n);

static session *session_new(network *n)
{
    session *s = (session *)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, sizeof *s);
    if (!s)
        return NULL;
    s->vtbl = session_vtbl;
    s->refs = 1;
    s->owner = n;
    Network_AddRef(n);
    InterlockedIncrement(&g_objects);
    return s;
}

/* ------------------------------------------------------------------ */
/* network                                                             */

static HRESULT __stdcall Network_QueryInterface(network *n, const GUID *riid, void **out)
{
    if (guid_eq(riid, &IID_Network) || guid_eq(riid, &IID_Unknown)) {
        *out = n;
        InterlockedIncrement(&n->refs);
        return S_OK;
    }
    *out = NULL;
    return E_NOINTERFACE;
}

static ULONG __stdcall Network_AddRef(network *n) { return InterlockedIncrement(&n->refs); }

static ULONG __stdcall Network_Release(network *n)
{
    LONG r = InterlockedDecrement(&n->refs);
    if (r == 0) {
        sr2_destroy(n->net);
        HeapFree(GetProcessHeap(), 0, n);
        InterlockedDecrement(&g_objects);
    }
    return r;
}

static HRESULT __stdcall Network_NotImpl(network *n) { (void)n; return E_NOTIMPL; }

static HRESULT __stdcall Network_SetAppGuid(network *n, const GUID *app)
{
    if (!app)
        return E_FAIL;
    n->app = *app;
    return S_OK;
}

static HRESULT __stdcall Network_EnumNone(network *n, void *cb, void *ctx)
{
    (void)n; (void)cb; (void)ctx;
    return S_OK;
}

/* {kind, arg1, arg2, ...}: 1 an address typed, 2 the internet, 3 the LAN */
static HRESULT __stdcall Network_OpenConnection(network *n, const DWORD *spec)
{
    int kind;
    const char *address = "";
    if (!spec)
        return E_FAIL;
    switch (spec[0]) {
    case 1: kind = SR2_KIND_DIRECT; address = (const char *)spec[1]; break;
    case 2:
        kind = SR2_KIND_INTERNET;
        if (network_setting("Staging")) {
            address = SR2_STAGING_DIRECTORY;
            log_line(NULL, "directory: " SR2_STAGING_DIRECTORY ", Staging = 1 in SR2.CFG");
        }
        break;
    case 3: kind = SR2_KIND_LAN; break;
    default: return E_FAIL;
    }
    return sr2_open(n->net, kind, address ? address : "", now_ms()) == SR2_OK ? S_OK : E_FAIL;
}

static HRESULT __stdcall Network_SelectConnection(network *n, DWORD index) { (void)n; (void)index; return S_OK; }

static HRESULT __stdcall Network_ConnectViaLobby(network *n, void *params, void **s, void **p)
{
    (void)n; (void)params; (void)s; (void)p;
    return E_FAIL;
}

typedef BOOL (__stdcall *enum_cb)(const BYTE *rec, void *ctx);

static HRESULT __stdcall Network_EnumSessions(network *n, enum_cb cb, void *ctx)
{
    int i, c = sr2_enum(n->net, now_ms(), n->found, SR2_MAX_SESSIONS);
    if (c == SR2_CONNECTING)
        return DPERR_CONNECTING;
    if (c < 0)
        return E_FAIL;
    n->nfound = c;
    for (i = 0; cb && i < c; i++) {
        BYTE rec[RECORD_SIZE];
        put_session_record(&n->found[i], rec);
        if (!cb(rec, ctx))
            break;
    }
    return S_OK;
}

static HRESULT __stdcall Network_JoinSession(network *n, const BYTE *rec, session **out)
{
    const sr2_session *s = NULL;
    int i, r;
    if (!rec || !out)
        return E_FAIL;
    for (i = 0; i < n->nfound; i++)
        if (memcmp(n->found[i].guid, rec + 0x10, 16) == 0)
            s = &n->found[i];
    if (!s)
        return DPERR_NOSESSIONS;
    r = sr2_join(n->net, s, now_ms());
    while (r == SR2_CONNECTING) {
        Sleep(5);
        r = sr2_join_status(n->net, now_ms());
    }
    if (r != SR2_OK)
        return r == SR2_REFUSED ? DPERR_ACCESSDENIED : DPERR_NOSESSIONS;
    *out = session_new(n);
    return *out ? S_OK : E_OUTOFMEMORY;
}

static HRESULT __stdcall Network_CreateSession(network *n, const BYTE *rec, session **out)
{
    char name[SR2_NAME_LEN];
    if (!rec || !out)
        return E_FAIL;
    memcpy(name, rec + 0x20, SR2_NAME_LEN);
    name[SR2_NAME_LEN - 1] = 0;
    if (sr2_host(n->net, name, (int)*(const DWORD *)(rec + 4), now_ms()) != SR2_OK)
        return E_FAIL;
    *out = session_new(n);
    return *out ? S_OK : E_OUTOFMEMORY;
}

static HRESULT __stdcall Network_GetCaps(network *n, DWORD *caps, DWORD flags)
{
    (void)n; (void)flags;
    if (!caps || caps[0] < 0x28)
        return E_INVALIDARG;
    memset(caps + 1, 0, 0x28 - 4);
    caps[1] = sr2_is_host(n->net) ? 2 : 0;          /* DPCAPS_ISHOST */
    caps[2] = SR2_MAX_PAYLOAD;
    caps[4] = SR2_MAX_PLAYERS;
    caps[6] = LATENCY_MS;
    caps[7] = 1;
    caps[9] = LATENCY_MS;
    return S_OK;
}

/* an added slot: the status line for the team room */
static HRESULT __stdcall Network_StatusLine(network *n, char *buf, DWORD len)
{
    const char *line;
    if (!buf || !len)
        return E_INVALIDARG;
    line = sr2_kind(n->net) == SR2_KIND_DIRECT ? sr2_status(n->net) : "";
    strncpy(buf, line, len - 1);
    buf[len - 1] = 0;
    return S_OK;
}

static const void *network_vtbl[15] = {
    Network_QueryInterface, Network_AddRef, Network_Release,
    Network_SetAppGuid,             /* +0x0c */
    Network_EnumNone,               /* +0x10 EnumModems */
    Network_EnumNone,               /* +0x14 EnumConnections */
    Network_OpenConnection,         /* +0x18 */
    Network_SelectConnection,       /* +0x1c */
    Network_ConnectViaLobby,        /* +0x20 */
    Network_EnumSessions,           /* +0x24 */
    Network_JoinSession,            /* +0x28 */
    Network_CreateSession,          /* +0x2c */
    Network_GetCaps,                /* +0x30 */
    Network_NotImpl,                /* +0x34 dtor */
    Network_StatusLine,             /* +0x38 ours */
};

static network *network_new(void)
{
    network *n = (network *)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, sizeof *n);
    if (!n)
        return NULL;
    n->vtbl = network_vtbl;
    n->refs = 1;
    n->net = sr2_create();
    if (!n->net) {
        HeapFree(GetProcessHeap(), 0, n);
        return NULL;
    }
    log_open();
    sr2_set_log(n->net, log_line, NULL);
    InterlockedIncrement(&g_objects);
    return n;
}

/* ------------------------------------------------------------------ */
/* the class factory and the exports                                   */

typedef struct {
    const void *vtbl;
} factory;

static HRESULT __stdcall Factory_QueryInterface(factory *f, const GUID *riid, void **out)
{
    if (guid_eq(riid, &IID_Factory) || guid_eq(riid, &IID_Unknown)) {
        *out = f;
        return S_OK;
    }
    *out = NULL;
    return E_NOINTERFACE;
}

static ULONG __stdcall Factory_AddRef(factory *f) { (void)f; return 2; }
static ULONG __stdcall Factory_Release(factory *f) { (void)f; return 1; }

static HRESULT __stdcall Factory_CreateInstance(factory *f, IUnknown *outer, const GUID *riid, void **out)
{
    network *n;
    HRESULT hr;
    (void)f;
    if (outer)
        return CLASS_E_NOAGGREGATION;
    n = network_new();
    if (!n)
        return E_OUTOFMEMORY;
    hr = Network_QueryInterface(n, riid, out);
    Network_Release(n);
    return hr;
}

static HRESULT __stdcall Factory_LockServer(factory *f, BOOL lock) { (void)f; (void)lock; return S_OK; }

static const void *factory_vtbl[5] = {
    Factory_QueryInterface, Factory_AddRef, Factory_Release, Factory_CreateInstance, Factory_LockServer,
};
static factory g_factory = {factory_vtbl};

HRESULT __stdcall DllGetClassObject(const GUID *rclsid, const GUID *riid, void **out)
{
    if (!guid_eq(rclsid, &CLSID_MGNetWk))
        return CLASS_E_CLASSNOTAVAILABLE;
    return Factory_QueryInterface(&g_factory, riid, out);
}

HRESULT __stdcall DllCanUnloadNow(void) { return g_objects == 0 ? S_OK : S_FALSE; }
HRESULT __stdcall DllRegisterServer(void) { return S_OK; }
HRESULT __stdcall DllUnregisterServer(void) { return S_OK; }

/* _CreateGameNetwork@4: the object without COM. */
HRESULT __stdcall CreateGameNetwork(void **out)
{
    if (!out)
        return E_FAIL;
    *out = network_new();
    return *out ? S_OK : E_OUTOFMEMORY;
}

BOOL WINAPI DllMain(HINSTANCE inst, DWORD reason, LPVOID reserved)
{
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        g_module = inst;
        DisableThreadLibraryCalls(inst);
    } else if (reason == DLL_PROCESS_DETACH && g_log) {
        fclose(g_log);
        g_log = NULL;
    }
    return TRUE;
}

/* The Windows release's exe: starts the patcher with the Python in
   _internal beside it, as

       _internal\pythonw.exe _internal\sr2-patcher.py [arguments]

   waits for it and returns its exit code. Everything the patcher does is
   in the script; this only finds it. The working directory is left as the
   caller's, so relative paths given as arguments mean what they did. */

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <wchar.h>

#define LONG_PATH 32768

static wchar_t here[LONG_PATH];
static wchar_t python[LONG_PATH];
static wchar_t script[LONG_PATH];
static wchar_t command[LONG_PATH];

static int fail(const wchar_t *what)
{
    MessageBoxW(NULL, what, L"SR2 Patcher", MB_OK | MB_ICONERROR);
    return 1;
}

/* The command line past the program's own name, per the rules Windows
   uses to split it: a quoted name runs to the closing quote, an unquoted
   one to the first blank. */
static const wchar_t *arguments(const wchar_t *line)
{
    if (*line == L'"') {
        for (line++; *line && *line != L'"'; line++)
            ;
        if (*line)
            line++;
    } else {
        while (*line && *line != L' ' && *line != L'\t')
            line++;
    }
    while (*line == L' ' || *line == L'\t')
        line++;
    return line;
}

static int present(const wchar_t *path)
{
    DWORD attributes = GetFileAttributesW(path);
    return attributes != INVALID_FILE_ATTRIBUTES
        && !(attributes & FILE_ATTRIBUTE_DIRECTORY);
}

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE previous, PWSTR unused, int show)
{
    STARTUPINFOW startup;
    PROCESS_INFORMATION process;
    DWORD length, code = 1;
    wchar_t *slash;

    (void)instance; (void)previous; (void)unused; (void)show;
    ZeroMemory(&startup, sizeof startup);
    startup.cb = sizeof startup;

    length = GetModuleFileNameW(NULL, here, LONG_PATH);
    if (length == 0 || length >= LONG_PATH)
        return fail(L"Cannot tell where this program is.");
    slash = wcsrchr(here, L'\\');
    if (!slash)
        return fail(L"Cannot tell where this program is.");
    *slash = L'\0';

    if (swprintf(python, LONG_PATH, L"%ls\\_internal\\pythonw.exe", here) < 0
        || swprintf(script, LONG_PATH, L"%ls\\_internal\\sr2-patcher.py", here) < 0)
        return fail(L"The path to this program is too long.");
    if (!present(python) || !present(script))
        return fail(L"The _internal folder beside this program is missing or "
                    L"incomplete. Unzip the whole download and run the program "
                    L"from the unzipped folder.");

    if (swprintf(command, LONG_PATH, L"\"%ls\" \"%ls\" %ls",
                 python, script, arguments(GetCommandLineW())) < 0)
        return fail(L"The command line is too long.");

    if (!CreateProcessW(python, command, NULL, NULL, FALSE, 0, NULL, NULL,
                        &startup, &process))
        return fail(L"Python in the _internal folder could not be started.");
    CloseHandle(process.hThread);
    WaitForSingleObject(process.hProcess, INFINITE);
    GetExitCodeProcess(process.hProcess, &code);
    CloseHandle(process.hProcess);
    return (int)code;
}

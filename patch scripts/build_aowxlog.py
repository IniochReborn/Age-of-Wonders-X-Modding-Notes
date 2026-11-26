#!/usr/bin/env python3
r"""
AoWxLog.dll - "X\Bug Report\Error Log.txt" in the game folder: every error + an Out-of-Sync recorder (2026-11-14).

v2 (2026-11-19, user): the log lives in X\Bug Report; every logged error carries a REF and, when a game is running, the
game is saved to "X\Bug Report\Error - <version> - <type> - REF <ref>.asg".
  REF = YYMMDD-HHMMSS-NNN (local time + 3 digits from tick count / process id / counter).
  arm (called by the VEH and the OoS dump): a save still waiting -> the error shares its REF; an error signature
  (code, address) already seen this session -> its old REF again, no second save; else a new REF, type text and
  g_pend = 1 (max MAX_SAVES per session).  Errors raised while the save itself runs never arm.
  The save runs on the MAIN thread from a 100 ms thread timer (SetTimer in DllMain, which runs on the main thread:
  AoWEPACK entry point): [AoWEPACK+0x1FA040] map != nil, engine [AoWEPACK+0x1FA048] VMT+0xAC = THSEngine.SaveHSM
  (eax engine, edx AnsiString name, push 0, push 0 - the autosave call) inside a Delphi try/except built from
  AoWEPACK's VCL30 thunks (RVA 0x10E8 HandleAnyException - reached through an E9 jmp patched at run time, it resumes
  at handler+5 - and RVA 0x1108 DoneExcept).  Version = the immediates in TAoWEngine.Create (RVA 0x97C18..).  The
  editor (AoWDevX) never saves.  A follow-up log line says what happened to the save.

User: "add an error log, a text file in the X folder called Error Log ... keep note of all error messages ... some kind
of Out of Sync logger (as part of the same error log) ... I dont want added error popups in game, but i want OoS log to
have more info than simply 'OoS'".

Hand-built PE (pure x86 from keystone, PIC with ebp = load delta, like AoWxShot.dll).  Loaded by a 5-byte stub on
AoWEPACK.dll's entry point (patch_error_log_v1.py), so the game AND the editor get it; without the DLL nothing happens.
No pop-ups, no game-state writes; the only files written are <exe folder>\X\Bug Report\Error Log.txt (append; restarted when it
exceeds 4 MB) and the bug-report saves next to it.

1. ERRORS - a vectored exception handler (first chance, returns CONTINUE_SEARCH so behaviour is unchanged):
   * Delphi exceptions (code 0x0EEDFADE: info[0] = raise address, info[1] = exception object, message AnsiString at
     [obj+4], class name ShortString at [[obj]-0x20]) -> "ERROR <class>: <message>  (raised at module+offset)".
     These are the texts of the game's "Error - ..." / "Access violation ..." dialogs, plus errors the game swallows.
   * hardware faults (code >= 0xC0000000) -> code, module+offset, read/write address, registers.
   Both get a "stack:" line (return-address candidates = stack dwords that point into executable image memory).
   Identical consecutive errors are counted, not repeated; at most 300 entries per session.
2. OUT OF SYNC - AoW's check: NetworkE.TSyncTE.Execute compares the value in the sync token with the local
   TPlayerControl.GetSyncValue = [map+0x230], the seed of the synced generator TAoWHSMap.Random 0x5577827C.  An OoS is
   therefore always "the machines consumed different synced random draws".  Two in-memory hooks (bytes verified, the
   files stay untouched):
   * TAoWHSMap.Random entry -> ring entry R {caller, range, seed before the draw}
   * the GetSyncValue call inside TSyncTE.Execute (Network.dpl RVA 0x43F8) -> ring entry S {local, received}; on a
     mismatch the log gets "OUT OF SYNC: local .. received .." and the last 2048 ring entries (oldest first).
   Compare the two machines' logs: the seed columns are identical up to the first draw that only one machine made (or
   made from a different caller) - that caller is the code that desynced.

3. FREEZE REPORT (2026-11-21, user: multiplayer game locked up with pulsing cursors, no pop-up, no error) - polled from
   the 100 ms main-thread timer, AoWx.exe only, nothing is written to the game:
   * automatic: network game ([map+0x13A]), the token executer is busy (lock count [exec+0x4C] != 0, or an event is
     mid-execution = status bit 2 of [exec+0x24], or the AI executer lock [aiexec+0x30] != 0) and its executed
     counter [exec+0x18] has not moved for FZ_SECS (15 s; 60 until user 11/21) -> one report per episode (max FZ_AUTO per session) + a follow-up
     line when the game moves on again (a real freeze has no follow-up).
   * manual: Ctrl+F while the game window is in front (max FZ_MAN per session); any game with a map.  A written
     manual report is confirmed in the game (fzdone, inside a Delphi try/except): status-bar text through map
     VMT+0x110 = TAbstractAoWHSMap.ShowMessage 0x557729B4 (eax map, edx AnsiString - what the save code calls
     for '<name> saved'), then the chat sound 'SFX\EVENTS\CHAT.WAV' (as exe DPlayChatMessage 0x413FDF).
     ShowMessage plays its own INFO1.WAV through AoWEPACK's import thunk of SoundP 'Sound.PlaySample' (RVA 0x2D04
     = jmp [slot]); the slot is pointed at a bare ret for the duration of the call and restored afterwards, and
     the saved pointer is what plays the chat sound.
     Automatic reports stay silent (they also fire on ordinary long waits).
   The report: map state, token executer (executed / status / lock / current seat), the waiting token events with
   their class names (what the game is waiting on), every token control (seat, active, queued events), AI executer,
   player control, communicator, combat, per-player turn flags, restore-handler state, DirectPlay state and the main
   thread's stack.  Export TestFreeze writes one on demand (CreateRemoteThread).
   TTokenExecuter (Network.dpl): +4 active TC, +8 executing TC, +0xC TC index, +0x10 event list, +0x14 TList of TCs,
   +0x18 executed, +0x1C rounds, +0x24 status set, +0x4C lock count, +0x50 system events, +0x54 hold.  TTokenControl:
   +4 event list, +8 manager, +0xC seat, +0x10 active.  Event list: [[list+8]+8] = TList (+4 items, +8 count).
4. MANUAL RESTORE (2026-11-21, user: "a Ctrl+R hotkey which restores the game ... i want the prompt") - Ctrl+R with the
   game window in front, network game, restore handler (patch_resync_net_v1) running and idle, nobody dropped:
   * DirectPlay host ([TGDPlay+0x1EF]): a Yes/No prompt "Restore the game for all players?" = a plain TMessageEventLog
     (class cell AoWEPACK RVA 0xFCCE4, Create RVA 0xFE080 eax class / dl 1 / ecx 0; +0x18 title, +0x20 TStrings
     VMT+0x34 Add, +0x24 layout, +0x25 style 2 = Yes+No, +0x26 result 3 = Yes) shown like the game's own exit prompt:
     map VMT+0x12C(eax map, edx log, cl 0, push cbObj, push cbFn), then log VMT+0x2C release.  The callback
     (eax cbObj, edx log) only raises a flag; the next timer tick re-checks the conditions, writes a freeze report
     ("requested with Ctrl+R") and sets the handler's V_OOS byte (V+1) to 6 = "host: start the restore" - the same
     value its own dialog's Restore button stores - after exe byte X_MAN 0x62FF7C = 0x4D, which the handler sends
     to every machine in its 'F' packet so that all waiting windows read "Host initiated a manual restore".
   * client: status-bar notice "Only the host can restore the game" (+ chat sound), nothing else.
   The base class is used on purpose: the handler's Yes/No hooks sit on TPlayerConnectionEventLog only.

Build: py -3.10 build_aowxlog.py [--check]   -> <game>\AoWxLog.dll
"""
import os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import game_file

OUT = game_file("AoWxLog.dll")
BASE, SEC_RVA = 0x6A600000, 0x1000
RING_N = 2048
MAX_LOG = 300
EP_RANDOM_RVA, NET_SYNC_RVA = 0x7827C, 0x43F8
MAP_RVA, ENGINE_RVA, HANDLEANY_RVA, DONEEXCEPT_RVA, VER_RVA = 0x1FA040, 0x1FA048, 0x10E8, 0x1108, 0x97C18
MAX_SAVES, NSIG = 20, 32
FZ_SECS, FZ_AUTO, FZ_MAN = 15, 30, 10
RIG_V_RVA, X_RIG, X_DPFORM = 0x1E9D20, 0x62FF60, 0x45A454
PLAY_THUNK_RVA = 0x2D04      # AoWEPACK: jmp [Sound.PlaySample import slot]
MSGLOG_CLS_RVA, MSGLOG_CREATE_RVA = 0xFCCE4, 0xFE080
RV_OOS, RV_DLG, RV_FROZEN, RV_STATE, RV_REALDR = 1, 3, 9, 10, 12   # restore handler V block (patch_resync_net_v1)
X_MAN, MAN_MARK = 0x62FF7C, 0x4D   # exe byte: "this restore was started by hand" - the handler sends it to every machine
LOGDIR = "X\\Bug Report"
IMPORTS = [
    ("kernel32.dll", ["GetModuleHandleA", "GetModuleFileNameA", "VirtualProtect", "VirtualQuery", "IsBadReadPtr",
                      "CreateFileA", "WriteFile", "CloseHandle", "SetFilePointer", "SetEndOfFile", "GetFileSize",
                      "GetLocalTime", "GetTickCount", "AddVectoredExceptionHandler", "lstrlenA", "lstrcmpA",
                      "CreateDirectoryA", "GetCurrentProcessId", "MoveFileA", "DeleteFileA", "IsBadWritePtr"]),
    ("user32.dll", ["wsprintfA", "SetTimer", "GetAsyncKeyState", "GetForegroundWindow", "GetWindowThreadProcessId"]),
    ("advapi32.dll", ["RegOpenKeyExA", "RegQueryValueExA", "RegCloseKey"]),
]


class Data(object):
    def __init__(self, va):
        self.va, self.b, self.sym = va, bytearray(), {}

    def add(self, name, blob, align=4):
        while len(self.b) % align:
            self.b.append(0)
        self.sym[name] = self.va + len(self.b)
        self.b += blob
        return self.sym[name]

    def var(self, name, size=4):
        return self.add(name, bytes(size))

    def s(self, name, text):
        return self.add(name, text.encode("latin1") + b"\0", 1)


def build_data(va):
    D = Data(va)
    for n in ("g_init", "g_inveh", "g_hdr", "g_h", "g_wr", "g_old", "g_nlog", "g_rep", "g_lastcode", "g_lastaddr",
              "g_rpos", "g_h2", "g_rback", "g_sorig", "g_cbase", "g_cname", "g_lp", "g_local", "g_remote", "g_dumps",
              "g_pend", "g_saving", "g_sok", "g_nsave", "g_nsig", "g_refn", "g_done"):
        D.var(n)
    for n in ("g_sln", "g_slm", "g_fzbase", "g_fzmap", "g_fzlast", "g_fzt0", "g_fzcnt", "g_fzrep", "g_fznum", "g_fzman",
              "g_fzkey", "g_fzpid", "g_fzi", "g_fztc", "g_fztmp", "g_fzok", "g_fzps", "g_fzslot", "g_fzmsgp", "g_rskey", "g_rsgo", "g_rsdlg", "g_rst0"):
        D.var(n)
    D.var("g_cls2", 68)
    D.var("g_st", 16)
    D.var("g_mbi", 28)
    D.var("g_path", 300)
    D.var("g_exe", 64)
    D.var("g_mpath", 264)
    D.var("g_cls", 68)
    D.var("g_line", 4096)
    D.var("g_ring", RING_N * 16)
    D.var("g_ref", 24)
    D.var("g_type", 48)
    D.var("g_dir", 264)
    D.var("g_sname", 8 + 640)
    D.var("g_sig", 32 * (NSIG + 1))
    D.s("s_file", LOGDIR + "\\Error Log.txt")
    D.s("f_oldlog", "%sX\\Error Log.txt")   # 11/20: a log from before the Bug Report folder is moved in (or deleted)
    D.s("f_oldlog2", "%s" + LOGDIR + "\\Error Log (old).txt")
    D.s("s_regkey", "Software\\Triumph Studios\\Age of Wonders X\\General")   # 11/20: AoWSetup Developer tab toggle
    D.s("s_regval", "AoWx Error Logs")                                       # REG_DWORD 0 = everything off; missing = on
    D.s("f_ref", "           REF %s\r\n")
    D.s("f_mkref", "%02u%02u%02u-%02u%02u%02u-%03u")
    D.s("f_save", "%s" + LOGDIR + "\\Error - 1.%u.%u - %s - REF %s.asg")
    D.s("f_saved", "REF %s: game saved as %s\r\n")
    D.s("f_sfail", "REF %s: saving the game FAILED (%s)\r\n")
    D.s("f_nosave", "REF %s: no save file (no game running)%.0s\r\n")
    D.s("f_xcode", "Exception %08X")
    D.s("s_exc", "Exception"); D.s("s_err", "Error"); D.s("s_oos", "Out of Sync")
    D.s("s_av", "Access Violation"); D.s("s_div", "Divide by Zero"); D.s("s_so", "Stack Overflow"); D.s("s_ill", "Illegal Instruction")
    D.s("s_aowe", "AoWEPACK.dll")
    D.s("s_net", "Network.dpl")
    D.s("s_unk", "?")
    D.s("s_none", "")
    D.s("f_hdr", "\r\n===== %s started %04u-%02u-%02u %02u:%02u:%02u =====\r\n")
    D.s("f_ts", "[%02u:%02u:%02u] ")
    D.s("f_delphi", "ERROR %.80s: %.600s  (raised at %s+0x%X)\r\n")
    D.s("f_native", "EXCEPTION %08X at %s+0x%X")
    D.s("f_av", " (%s of address %08X)")
    D.s("s_read", "read"); D.s("s_write", "write"); D.s("s_exec", "execute")
    D.s("f_regs", "\r\n           eax=%08X ebx=%08X ecx=%08X edx=%08X esi=%08X edi=%08X ebp=%08X esp=%08X\r\n")
    D.s("f_stk0", "           stack:")
    D.s("f_stk", " %s+0x%X")
    D.s("s_crlf", "\r\n")
    D.s("f_rep", "           (the previous error repeated %u more times)\r\n")
    D.s("f_max", "           (error limit for this session reached - further errors are not logged)\r\n")
    D.s("f_oos", "*** OUT OF SYNC ***  REF %s  local sync value %08X, value received %08X; synced random draws so far: %u\r\n"
                 "           Last %u synced random draws (R) and sync checks (S), oldest first. Compare with the other\r\n"
                 "           player's log: the first line that differs is where the game states split.\r\n")
    D.s("f_r", "           R #%u seed %08X range %u caller %s+0x%X\r\n")
    D.s("f_s", "           S #%u local %08X received %08X %s\r\n")
    D.s("s_ok", "ok"); D.s("s_bad", "MISMATCH")
    D.s("f_end", "           (end of the out-of-sync record)\r\n")
    D.s("f_fz1", "*** GAME STATE REPORT ***  %s; no token progress for %u s\r\n")
    D.s("s_fzauto", "automatic (the game has waited on a locked action for %u seconds - normal while a player decides on "
                    "or fights a battle; a follow-up line appears if the game moves on)" % FZ_SECS)
    D.s("s_fzman", "requested with Ctrl+F")
    D.s("f_fzrel", "game state report follow-up: the game moved on after about %u s\r\n")
    D.s("f_fzmap", "  map: turn player %d, local player %d, combat %08X, +118 %u, +11A %u, tactical map %08X, network %u, "
                   "sync seed %08X, play mode %u, flags %02X\r\n")
    D.s("f_fzex", "  token executer: executed %u, rounds %u, status %02X (2 = event mid-execution), lock count %d, hold %u, "
                  "current seat index %d, executing %u, tries %u\r\n")
    D.s("f_fztc", "  token control %u @%08X: seat %d, active %u%s\r\n")
    D.s("s_cur", "  <- current")
    D.s("f_fzpl", "  player %u: turn ended %u, +44 %u, +45 %u, kind %u\r\n")
    D.s("f_evl", "  %s: %d waiting\r\n")
    D.s("f_hbad", "  %s @%08X: not readable\r\n")
    D.s("f_hobj", "  %s @%08X (%s)\r\n")
    D.s("f_hrow", "    +%02X  %08X %08X %08X %08X\r\n")
    D.s("f_fzend", "           (end of the game state report)\r\n")
    D.s("s_l_tm", "token manager"); D.s("s_l_ex", "token executer"); D.s("s_l_ev", "events of the current seat")
    D.s("s_l_sys", "system events"); D.s("s_l_tcev", "  its events"); D.s("s_l_event", "event")
    D.s("s_l_ai", "AI executer (+30 lock)"); D.s("s_l_pc", "player control"); D.s("s_l_comm", "communicator")
    D.s("s_l_cb", "combat"); D.s("s_l_cd", "combat data"); D.s("s_l_rig", "restore handler state")
    D.s("s_l_rigx", "restore handler exe state"); D.s("s_l_dp", "DirectPlay state (+1B0)")
    D.s("s_fzres", "requested with Ctrl+R (restore)")
    D.s("s_l_evu", "first event: object at +1C (combat unit of a move)"); D.s("s_l_evhs", "its +60 (unit on the battlefield)")
    D.s("s_l_evtu", "its +4C (unit)")
    for nm, txt in (("a_fzmsg", "Game state data recorded to Error Log"), ("a_chatwav", "SFX\\EVENTS\\CHAT.WAV"),
                    ("a_rstitle", "Restore Game"), ("a_rsask", "Restore the game for all players?"),
                    ("a_rsnohost", "Only the host can restore the game")):
        D.add(nm, struct.pack("<iI", -1, len(txt)) + txt.encode("latin1") + b"\0")     # constant Delphi AnsiString (chars at +8)
    return D


def asm_text(D, I, GD):
    v = lambda n: "dword ptr [ebp + %#x]" % D.sym[n]      # noqa: E731
    a = lambda n: "%#x" % D.sym[n]                          # noqa: E731
    imp = lambda n: "dword ptr [ebp + %#x]" % I[n]          # noqa: E731
    nl = chr(10)

    def P(fmt, *args):
        """wsprintfA(g_lp, fmt, args...) + wflush; 'b:[..]' / 'sb:[..]' = zero / sign extended byte (uses eax)"""
        o = []
        for x in reversed(args):
            if x.startswith("b:"): o += ["movzx eax, byte ptr " + x[2:], "push eax"]
            elif x.startswith("sb:"): o += ["movsx eax, byte ptr " + x[3:], "push eax"]
            else: o.append("push " + x)
        o += ["lea eax, [ebp + %s]" % a(fmt), "push eax", "push " + v("g_lp"), "call " + imp("wsprintfA"),
              "add esp, %#x" % (4 * (len(args) + 2)), "call wflush"]
        return nl.join("        " + x for x in o)

    def OK(reg, size, fail):
        return nl.join("        " + x for x in ["mov eax, " + reg, "mov edx, %#x" % size, "call rdok", "test eax, eax", "jnz " + fail])

    def RD(dst, src, off, fail):
        return nl.join("        " + x for x in ["lea eax, [%s + %#x]" % (src, off), "mov edx, 0x4", "call rdok", "test eax, eax",
                                                "jnz " + fail, "mov %s, dword ptr [%s + %#x]" % (dst, src, off)])

    def HEX(ptr, size, label, fn="hexobj"):
        return nl.join("        " + x for x in ["mov eax, " + ptr, "mov edx, %#x" % size, "lea ecx, [ebp + %s]" % a(label), "call " + fn])

    d = lambda x: "dword ptr [%s]" % x                      # noqa: E731
    FZ = f"""
    rdok:
        cmp eax, 0x10000
        jb rk_bad
        push edx
        push eax
        call {imp('IsBadReadPtr')}
        ret
    rk_bad:
        mov eax, 0x1
        ret

    clsname:
        push esi
        push edi
        mov esi, eax
        mov edx, 0x4
        call rdok
        test eax, eax
        jnz cn_u
        mov esi, dword ptr [esi]
        lea eax, [esi - 0x20]
        mov edx, 0x4
        call rdok
        test eax, eax
        jnz cn_u
        mov esi, dword ptr [esi - 0x20]
        mov eax, esi
        mov edx, 0x40
        call rdok
        test eax, eax
        jnz cn_u
        movzx ecx, byte ptr [esi]
        test ecx, ecx
        jz cn_u
        cmp ecx, 0x3c
        ja cn_u
        inc esi
        lea edi, [ebp + {a('g_cls2')}]
    cn_l:
        mov al, byte ptr [esi]
        cmp al, 0x30
        jb cn_u
        cmp al, 0x7a
        ja cn_u
        mov byte ptr [edi], al
        inc esi
        inc edi
        dec ecx
        jnz cn_l
        mov byte ptr [edi], 0x0
        lea eax, [ebp + {a('g_cls2')}]
        jmp cn_r
    cn_u:
        lea eax, [ebp + {a('s_unk')}]
    cn_r:
        pop edi
        pop esi
        ret

    hexobj:
        push ebx
        push esi
        push edi
        mov esi, eax
        mov edi, edx
        mov ebx, ecx
        call rdok
        test eax, eax
        jz ho_ok
{P('f_hbad', 'ebx', 'esi')}
        jmp ho_r
    ho_ok:
        mov eax, esi
        call clsname
{P('f_hobj', 'ebx', 'esi', 'eax')}
        xor ebx, ebx
    ho_l:
        cmp ebx, edi
        jae ho_r
{P('f_hrow', 'ebx', d('esi + ebx'), d('esi + ebx + 0x4'), d('esi + ebx + 0x8'), d('esi + ebx + 0xc'))}
        add ebx, 0x10
        jmp ho_l
    ho_r:
        pop edi
        pop esi
        pop ebx
        ret

    evlist:
        push ebx
        push esi
        push edi
        mov ebx, ecx
        mov esi, eax
{OK('esi', 12, 'el_r')}
        mov esi, dword ptr [esi + 0x8]
{OK('esi', 12, 'el_r')}
        mov esi, dword ptr [esi + 0x8]
{OK('esi', 12, 'el_r')}
        mov edi, dword ptr [esi + 0x8]
        mov esi, dword ptr [esi + 0x4]
{P('f_evl', 'ebx', 'edi')}
        cmp edi, 0x0
        jle el_r
        cmp edi, 0x3
        jbe el_l
        mov edi, 0x3
    el_l:
{OK('esi', 4, 'el_r')}
{HEX(d('esi'), 0x60, 's_l_event')}
        add esi, 0x4
        dec edi
        jnz el_l
    el_r:
        pop edi
        pop esi
        pop ebx
        ret

    fzreport:
        pushal
        mov esi, eax
        mov edi, edx
        mov eax, 0x1
        xchg eax, {v('g_inveh')}
        test eax, eax
        jnz fr_r
        call wopen
        cmp {v('g_h')}, 0x0
        je fr_x
        lea eax, [ebp + {a('g_line')}]
        mov {v('g_lp')}, eax
        call tstamp
{P('f_fz1', 'esi', 'edi')}
        mov ebx, {v('g_fzmap')}
{OK('ebx', 0x250, 'fr_end')}
{P('f_fzmap', 'sb:[ebx + 0xa4]', 'sb:[ebx + 0xa5]', d('ebx + 0x120'), 'b:[ebx + 0x118]', 'b:[ebx + 0x11a]', d('ebx + 0x11c'),
   'b:[ebx + 0x13a]', d('ebx + 0x230'), 'b:[ebx + 0x239]', 'b:[ebx + 0x3c]')}
{RD('esi', 'ebx', 0x23c, 'fr_ai')}
{HEX('esi', 0x30, 's_l_tm')}
{RD('esi', 'esi', 0x4, 'fr_ai')}
{OK('esi', 0x60, 'fr_ai')}
{P('f_fzex', d('esi + 0x18'), d('esi + 0x1c'), 'b:[esi + 0x24]', d('esi + 0x4c'), 'b:[esi + 0x54]', d('esi + 0xc'),
   'b:[esi + 0x48]', d('esi + 0x20'))}
{HEX('esi', 0x60, 's_l_ex')}
{HEX(d('esi + 0x10'), 0, 's_l_ev', 'evlist')}
        mov ebx, dword ptr [esi + 0x10]
{OK('ebx', 12, 'fr_u9')}
        mov ebx, dword ptr [ebx + 0x8]
{OK('ebx', 12, 'fr_u9')}
        mov ebx, dword ptr [ebx + 0x8]
{OK('ebx', 12, 'fr_u9')}
        cmp dword ptr [ebx + 0x8], 0x0
        jle fr_u9
        mov ebx, dword ptr [ebx + 0x4]
{OK('ebx', 4, 'fr_u9')}
        mov ebx, dword ptr [ebx]
{OK('ebx', 0x20, 'fr_u9')}
        mov ebx, dword ptr [ebx + 0x1c]
{OK('ebx', 0x70, 'fr_u9')}
{HEX('ebx', 0x70, 's_l_evu')}
{HEX(d('ebx + 0x60'), 0x30, 's_l_evhs')}
{HEX(d('ebx + 0x4c'), 0x50, 's_l_evtu')}
    fr_u9:
{HEX(d('esi + 0x50'), 0, 's_l_sys', 'evlist')}
        mov edi, dword ptr [esi + 0x14]
{OK('edi', 12, 'fr_ai')}
        mov ebx, dword ptr [edi + 0x8]
        mov edi, dword ptr [edi + 0x4]
        cmp ebx, 0x0
        jle fr_ai
        cmp ebx, 0x10
        jbe fr_t0
        mov ebx, 0x10
    fr_t0:
        mov {v('g_fzi')}, 0x0
    fr_tl:
{OK('edi', 4, 'fr_ai')}
        mov eax, dword ptr [edi]
        mov {v('g_fztc')}, eax
        mov edx, 0x14
        call rdok
        test eax, eax
        jnz fr_tn
        mov ecx, {v('g_fztc')}
        lea edx, [ebp + {a('s_none')}]
        cmp ecx, dword ptr [esi + 0x4]
        jne fr_t1
        lea edx, [ebp + {a('s_cur')}]
    fr_t1:
{P('f_fztc', v('g_fzi'), 'ecx', d('ecx + 0xc'), 'b:[ecx + 0x10]', 'edx')}
        mov ecx, {v('g_fztc')}
        mov eax, dword ptr [ecx + 0x4]
        lea ecx, [ebp + {a('s_l_tcev')}]
        call evlist
    fr_tn:
        add edi, 0x4
        inc {v('g_fzi')}
        dec ebx
        jnz fr_tl
    fr_ai:
        mov ebx, {v('g_fzmap')}
{HEX(d('ebx + 0x128'), 0x40, 's_l_ai')}
{HEX(d('ebx + 0x244'), 0x30, 's_l_pc')}
{HEX(d('ebx + 0x240'), 0x30, 's_l_comm')}
        cmp dword ptr [ebx + 0x120], 0x0
        je fr_pl
{HEX(d('ebx + 0x120'), 0x40, 's_l_cb')}
        mov esi, dword ptr [ebx + 0x120]
{RD('esi', 'esi', 0xc, 'fr_pl')}
{HEX('esi', 0x50, 's_l_cd')}
    fr_pl:
{RD('esi', 'ebx', 0x140, 'fr_rig')}
{RD('esi', 'esi', 0x8, 'fr_rig')}
{OK('esi', 12, 'fr_rig')}
        mov edi, dword ptr [esi + 0x4]
        mov ebx, dword ptr [esi + 0x8]
        cmp ebx, 0x0
        jle fr_rig
        cmp ebx, 0x10
        jbe fr_p0
        mov ebx, 0x10
    fr_p0:
        mov {v('g_fzi')}, 0x0
    fr_p1:
{OK('edi', 4, 'fr_rig')}
        mov eax, dword ptr [edi]
        mov {v('g_fztc')}, eax
        mov edx, 0xb0
        call rdok
        test eax, eax
        jnz fr_pn
        mov ecx, {v('g_fztc')}
{P('f_fzpl', v('g_fzi'), 'b:[ecx + 0x2c]', 'b:[ecx + 0x44]', 'b:[ecx + 0x45]', 'b:[ecx + 0xa7]')}
    fr_pn:
        add edi, 0x4
        inc {v('g_fzi')}
        dec ebx
        jnz fr_p1
    fr_rig:
        mov eax, {v('g_fzbase')}
        add eax, {RIG_V_RVA:#x}
        mov edx, 0x30
        lea ecx, [ebp + {a('s_l_rig')}]
        call hexobj
{HEX('%#x' % X_RIG, 0x20, 's_l_rigx')}
        mov esi, {X_DPFORM:#x}
{OK('esi', 4, 'fr_stk')}
        mov esi, dword ptr [esi]
{OK('esi', 4, 'fr_stk')}
        mov esi, dword ptr [esi]
{RD('esi', 'esi', 0x44, 'fr_stk')}
        lea eax, [esi + 0x1b0]
        mov edx, 0x50
        lea ecx, [ebp + {a('s_l_dp')}]
        call hexobj
    fr_stk:
        mov eax, esp
        mov edx, 0x600
        call rdok
        test eax, eax
        jnz fr_s1
        mov {v('g_sln')}, 0x180
        mov {v('g_slm')}, 0x28
    fr_s1:
        mov eax, esp
        call stackline
        call wflush
        mov {v('g_sln')}, 0x40
        mov {v('g_slm')}, 0xc
    fr_end:
        mov {v('g_fzok')}, 0x1
{P('f_fzend')}
        call wclose
    fr_x:
        mov {v('g_inveh')}, 0x0
    fr_r:
        popal
        ret

    fznote:
        mov {v('g_fztmp')}, eax
        mov eax, 0x1
        xchg eax, {v('g_inveh')}
        test eax, eax
        jnz fn_r
        call wopen
        cmp {v('g_h')}, 0x0
        je fn_x
        lea eax, [ebp + {a('g_line')}]
        mov {v('g_lp')}, eax
        call tstamp
{P('f_fzrel', v('g_fztmp'))}
        call wclose
    fn_x:
        mov {v('g_inveh')}, 0x0
    fn_r:
        ret

    fzfind:
        mov al, byte ptr [ebp + {D.sym['g_exe'] + 3:#x}]
        or al, 0x20
        cmp al, 0x64
        je ff_no
        lea eax, [ebp + {a('s_aowe')}]
        push eax
        call {imp('GetModuleHandleA')}
        test eax, eax
        jz ff_no
        mov {v('g_fzbase')}, eax
        mov ebx, dword ptr [eax + {MAP_RVA:#x}]
        test ebx, ebx
        jz ff_no
        mov {v('g_fzmap')}, ebx
        ret
    ff_no:
        xor ebx, ebx
        ret

    fztick:
        call fzfind
        test ebx, ebx
        jnz ft_map
        mov {v('g_fzt0')}, 0x0
        mov {v('g_fzrep')}, 0x0
        mov {v('g_rsdlg')}, 0x0
        mov {v('g_rsgo')}, 0x0
        ret
    ft_map:
        push 0x11
        call {imp('GetAsyncKeyState')}
        test ah, 0x80
        jz ft_nokey
        push 0x46
        call {imp('GetAsyncKeyState')}
        test ah, 0x80
        jz ft_nokey
        cmp {v('g_fzkey')}, 0x0
        jne ft_auto
        mov {v('g_fzkey')}, 0x1
        call {imp('GetForegroundWindow')}
        test eax, eax
        jz ft_auto
        lea ecx, [ebp + {a('g_fzpid')}]
        push ecx
        push eax
        call {imp('GetWindowThreadProcessId')}
        call {imp('GetCurrentProcessId')}
        cmp eax, {v('g_fzpid')}
        jne ft_auto
        cmp {v('g_fzman')}, {FZ_MAN:#x}
        jae ft_auto
        inc {v('g_fzman')}
        call {imp('GetTickCount')}
        xor edx, edx
        cmp {v('g_fzt0')}, 0x0
        je ft_k1
        sub eax, {v('g_fzt0')}
        mov ecx, 0x3e8
        div ecx
        mov edx, eax
    ft_k1:
        lea eax, [ebp + {a('s_fzman')}]
        mov {v('g_fzok')}, 0x0
        call fzreport
        cmp {v('g_fzok')}, 0x0
        je ft_auto
        lea eax, [ebp + {D.sym['a_fzmsg'] + 8:#x}]
        mov {v('g_fzmsgp')}, eax
        call fzdone
        jmp ft_auto
    ft_nokey:
        mov {v('g_fzkey')}, 0x0
    ft_auto:
        call rstick
        call {imp('GetTickCount')}
        mov edi, eax
        sub eax, {v('g_fzlast')}
        cmp eax, 0x3e8
        jb ft_r
        mov {v('g_fzlast')}, edi
        mov ebx, {v('g_fzmap')}
{OK('ebx', 0x250, 'ft_r')}
        mov esi, dword ptr [ebx + 0x23c]
{OK('esi', 8, 'ft_idle')}
        mov esi, dword ptr [esi + 0x4]
{OK('esi', 0x60, 'ft_idle')}
        cmp dword ptr [esi + 0x4c], 0x0
        jne ft_busy
        test byte ptr [esi + 0x24], 0x2
        jnz ft_busy
        mov eax, dword ptr [ebx + 0x128]
        mov {v('g_fztmp')}, eax
        mov edx, 0x34
        call rdok
        test eax, eax
        jnz ft_idle
        mov eax, {v('g_fztmp')}
        cmp dword ptr [eax + 0x30], 0x0
        jne ft_busy
    ft_idle:
        call ft_moved
        mov {v('g_fzt0')}, 0x0
        ret
    ft_busy:
        mov eax, dword ptr [esi + 0x18]
        cmp {v('g_fzt0')}, 0x0
        je ft_start
        cmp eax, {v('g_fzcnt')}
        jne ft_prog
        cmp {v('g_fzrep')}, 0x0
        jne ft_r
        mov eax, edi
        sub eax, {v('g_fzt0')}
        cmp eax, {FZ_SECS * 1000:#x}
        jb ft_r
        cmp byte ptr [ebx + 0x13a], 0x0
        je ft_r
        cmp {v('g_fznum')}, {FZ_AUTO:#x}
        jae ft_r
        inc {v('g_fznum')}
        mov {v('g_fzrep')}, 0x1
        lea eax, [ebp + {a('s_fzauto')}]
        mov edx, {FZ_SECS:#x}
        call fzreport
    ft_r:
        ret
    ft_prog:
        push eax
        call ft_moved
        pop eax
    ft_start:
        mov {v('g_fzcnt')}, eax
        test edi, edi
        jnz ft_s1
        inc edi
    ft_s1:
        mov {v('g_fzt0')}, edi
        ret
    ft_moved:
        cmp {v('g_fzrep')}, 0x0
        je ft_m1
        mov {v('g_fzrep')}, 0x0
        mov eax, edi
        sub eax, {v('g_fzt0')}
        xor edx, edx
        mov ecx, 0x3e8
        div ecx
        call fznote
    ft_m1:
        ret

    fzdone:
        mov esi, {v('g_fzbase')}
        mov {v('g_fzslot')}, 0x0
        cmp word ptr [esi + {HANDLEANY_RVA:#x}], 0x25ff
        jne fd_r
        cmp word ptr [esi + {DONEEXCEPT_RVA:#x}], 0x25ff
        jne fd_r
        cmp word ptr [esi + {PLAY_THUNK_RVA:#x}], 0x25ff
        jne fd_r
        mov edi, dword ptr [esi + {PLAY_THUNK_RVA + 2:#x}]
        push 0x4
        push edi
        call {imp('IsBadWritePtr')}
        test eax, eax
        jnz fd_r
        mov eax, dword ptr [edi]
        test eax, eax
        jz fd_r
        mov {v('g_fzps')}, eax
        lea eax, [esi + {HANDLEANY_RVA:#x}]
        lea ecx, [ebp + fd_exc]
        sub eax, ecx
        sub eax, 0x5
        mov dword ptr [ecx + 0x1], eax
        lea eax, [esi + {DONEEXCEPT_RVA:#x}]
        mov {v('g_done')}, eax
        mov {v('g_saving')}, 0x1
        mov {v('g_fzslot')}, edi
        lea eax, [ebp + fd_ret]
        mov dword ptr [edi], eax
        xor eax, eax
        push ebp
        lea ecx, [ebp + fd_exc]
        push ecx
        push dword ptr fs:[eax]
        mov dword ptr fs:[eax], esp
        mov eax, {v('g_fzmap')}
        mov edx, {v('g_fzmsgp')}
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x110]
        mov eax, {v('g_fzps')}
        mov ecx, {v('g_fzslot')}
        mov dword ptr [ecx], eax
        lea eax, [ebp + {D.sym['a_chatwav'] + 8:#x}]
        call {v('g_fzps')}
        xor eax, eax
        pop edx
        pop ecx
        pop ecx
        mov dword ptr fs:[eax], edx
        jmp fd_after
    fd_exc:
        .byte 0xe9, 0x0, 0x0, 0x0, 0x0
        call {v('g_done')}
    fd_after:
        mov eax, {v('g_fzps')}
        mov ecx, {v('g_fzslot')}
        mov dword ptr [ecx], eax
        mov {v('g_saving')}, 0x0
    fd_r:
        ret
    fd_ret:
        ret

    rs_can:
        mov ebx, {v('g_fzmap')}
{OK('ebx', 0x250, 'rc_no')}
        cmp byte ptr [ebx + 0x13a], 0x0
        je rc_no
        mov esi, {v('g_fzbase')}
        add esi, {RIG_V_RVA:#x}
{OK('esi', 0x10, 'rc_no')}
        cmp dword ptr [esi + {RV_REALDR:#x}], 0x0
        je rc_no
        cmp byte ptr [esi + {RV_OOS:#x}], 0x0
        jne rc_no
        cmp byte ptr [esi + {RV_DLG:#x}], 0x0
        jne rc_no
        cmp byte ptr [esi + {RV_FROZEN:#x}], 0x0
        jne rc_no
        cmp byte ptr [esi + {RV_STATE:#x}], 0x0
        jne rc_no
        mov esi, {X_RIG:#x}
{OK('esi', 4, 'rc_h')}
        mov esi, dword ptr [esi]
        test esi, esi
        jz rc_h
{OK('esi', 4, 'rc_no')}
        cmp byte ptr [esi], 0x0
        jne rc_no
    rc_h:
        mov esi, {X_DPFORM:#x}
{OK('esi', 4, 'rc_no')}
        mov esi, dword ptr [esi]
{OK('esi', 4, 'rc_no')}
        mov esi, dword ptr [esi]
{RD('esi', 'esi', 0x44, 'rc_no')}
        lea eax, [esi + 0x1ec]
        mov edx, 0x4
        call rdok
        test eax, eax
        jnz rc_no
        cmp byte ptr [esi + 0x1ef], 0x0
        je rc_nh
        mov eax, 0x1
        ret
    rc_nh:
        mov eax, 0x2
        ret
    rc_no:
        xor eax, eax
        ret

    rstick:
        cmp {v('g_rsgo')}, 0x0
        je rs_key
        mov {v('g_rsgo')}, 0x0
        call rs_can
        cmp eax, 0x1
        jne rs_key
        lea eax, [ebp + {a('s_fzres')}]
        xor edx, edx
        call fzreport
        mov byte ptr [{X_MAN:#x}], {MAN_MARK:#x}
        mov eax, {v('g_fzbase')}
        mov byte ptr [eax + {RIG_V_RVA + RV_OOS:#x}], 0x6
        ret
    rs_key:
        push 0x11
        call {imp('GetAsyncKeyState')}
        test ah, 0x80
        jz rs_up
        push 0x52
        call {imp('GetAsyncKeyState')}
        test ah, 0x80
        jz rs_up
        cmp {v('g_rskey')}, 0x0
        jne rs_r
        mov {v('g_rskey')}, 0x1
        call {imp('GetForegroundWindow')}
        test eax, eax
        jz rs_r
        lea ecx, [ebp + {a('g_fzpid')}]
        push ecx
        push eax
        call {imp('GetWindowThreadProcessId')}
        call {imp('GetCurrentProcessId')}
        cmp eax, {v('g_fzpid')}
        jne rs_r
        call rs_can
        cmp eax, 0x1
        je rs_ask
        cmp eax, 0x2
        jne rs_r
        lea eax, [ebp + {D.sym['a_rsnohost'] + 8:#x}]
        mov {v('g_fzmsgp')}, eax
        call fzdone
        ret
    rs_ask:
        call rsprompt
        ret
    rs_up:
        mov {v('g_rskey')}, 0x0
    rs_r:
        ret

    rsprompt:
        cmp {v('g_rsdlg')}, 0x0
        je rp_go
        call {imp('GetTickCount')}
        sub eax, {v('g_rst0')}
        cmp eax, 0x1d4c0
        jb rp_r
    rp_go:
        mov esi, {v('g_fzbase')}
        cmp word ptr [esi + {HANDLEANY_RVA:#x}], 0x25ff
        jne rp_r
        cmp word ptr [esi + {DONEEXCEPT_RVA:#x}], 0x25ff
        jne rp_r
        cmp dword ptr [esi + {MSGLOG_CREATE_RVA:#x}], 0x6aec8b55
        jne rp_r
        lea eax, [esi + {HANDLEANY_RVA:#x}]
        lea ecx, [ebp + rp_exc]
        sub eax, ecx
        sub eax, 0x5
        mov dword ptr [ecx + 0x1], eax
        lea eax, [esi + {DONEEXCEPT_RVA:#x}]
        mov {v('g_done')}, eax
        call {imp('GetTickCount')}
        mov {v('g_rst0')}, eax
        mov {v('g_saving')}, 0x1
        xor eax, eax
        push ebp
        lea ecx, [ebp + rp_exc]
        push ecx
        push dword ptr fs:[eax]
        mov dword ptr fs:[eax], esp
        mov eax, dword ptr [esi + {MSGLOG_CLS_RVA:#x}]
        mov dl, 0x1
        xor ecx, ecx
        lea edi, [esi + {MSGLOG_CREATE_RVA:#x}]
        call edi
        mov edi, eax
        mov byte ptr [edi + 0x25], 0x2
        mov byte ptr [edi + 0x24], 0x0
        lea eax, [ebp + {D.sym['a_rstitle'] + 8:#x}]
        mov dword ptr [edi + 0x18], eax
        mov eax, dword ptr [edi + 0x20]
        lea edx, [ebp + {D.sym['a_rsask'] + 8:#x}]
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x34]
        mov {v('g_rsdlg')}, 0x1
        push {v('g_fzmap')}
        lea eax, [ebp + rs_cb]
        push eax
        xor ecx, ecx
        mov edx, edi
        mov eax, {v('g_fzmap')}
        mov esi, dword ptr [eax]
        call dword ptr [esi + 0x12c]
        mov eax, edi
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0x2c]
        xor eax, eax
        pop edx
        pop ecx
        pop ecx
        mov dword ptr fs:[eax], edx
        jmp rp_after
    rp_exc:
        .byte 0xe9, 0x0, 0x0, 0x0, 0x0
        call {v('g_done')}
    rp_after:
        mov {v('g_saving')}, 0x0
    rp_r:
        ret

    rs_cb:
        push ebp
        call {GD:#x}
        mov {v('g_rsdlg')}, 0x0
        cmp byte ptr [edx + 0x26], 0x3
        jne cb_r
        mov {v('g_rsgo')}, 0x1
    cb_r:
        pop ebp
        ret

    testfreeze:
        pushal
        call {GD:#x}
        call fzfind
        test ebx, ebx
        jz tf_r
        lea eax, [ebp + {a('s_fzman')}]
        xor edx, edx
        call fzreport
    tf_r:
        popal
        xor eax, eax
        ret 0x4
    """
    return f"""
    dllmain:
        cmp dword ptr [esp + 0x8], 0x1
        jne dm_ok
        pushal
        call {GD:#x}
        cmp {v('g_init')}, 0x0
        jne dm_done
        mov {v('g_init')}, 0x1
        mov {v('g_sln')}, 0x40
        mov {v('g_slm')}, 0xc
        push 0x104
        lea eax, [ebp + {a('g_path')}]
        push eax
        push 0x0
        call {imp('GetModuleFileNameA')}
        lea esi, [ebp + {a('g_path')}]
        mov edi, esi
    dm_p1:
        mov al, byte ptr [esi]
        test al, al
        jz dm_p2
        inc esi
        cmp al, 0x5c
        jne dm_p1
        mov edi, esi
        jmp dm_p1
    dm_p2:
        lea esi, [ebp + {a('g_path')}]
        lea edx, [ebp + {a('g_dir')}]
    dm_d1:
        cmp esi, edi
        jae dm_d2
        mov al, byte ptr [esi]
        mov byte ptr [edx], al
        inc esi
        inc edx
        jmp dm_d1
    dm_d2:
        mov byte ptr [edx], 0x0
        mov esi, edi
        lea edx, [ebp + {a('g_exe')}]
        mov ecx, 0x3f
    dm_c1:
        mov al, byte ptr [esi]
        mov byte ptr [edx], al
        test al, al
        jz dm_c2
        inc esi
        inc edx
        dec ecx
        jnz dm_c1
        mov byte ptr [edx], 0x0
    dm_c2:
        lea esi, [ebp + {a('s_file')}]
    dm_c3:
        mov al, byte ptr [esi]
        mov byte ptr [edi], al
        inc esi
        inc edi
        test al, al
        jnz dm_c3
        mov byte ptr [edi - 0xf], 0x0
        push 0x0
        lea eax, [ebp + {a('g_path')}]
        push eax
        call {imp('CreateDirectoryA')}
        mov byte ptr [edi - 0xf], 0x5c
        lea eax, [ebp + {a('g_dir')}]
        push eax
        lea eax, [ebp + {a('f_oldlog')}]
        push eax
        lea eax, [ebp + {a('g_mpath')}]
        push eax
        call {imp('wsprintfA')}
        add esp, 0xc
        lea eax, [ebp + {a('g_path')}]
        push eax
        lea eax, [ebp + {a('g_mpath')}]
        push eax
        call {imp('MoveFileA')}
        test eax, eax
        jnz dm_mv
        lea eax, [ebp + {a('g_dir')}]
        push eax
        lea eax, [ebp + {a('f_oldlog2')}]
        push eax
        lea eax, [ebp + {a('g_line')}]
        push eax
        call {imp('wsprintfA')}
        add esp, 0xc
        lea eax, [ebp + {a('g_line')}]
        push eax
        lea eax, [ebp + {a('g_mpath')}]
        push eax
        call {imp('MoveFileA')}
        test eax, eax
        jnz dm_mv
        lea eax, [ebp + {a('g_mpath')}]
        push eax
        call {imp('DeleteFileA')}
    dm_mv:
        mov byte ptr [ebp + {a('g_line')}], 0x0
        lea eax, [ebp + {a('g_mbi')}]
        push eax
        push 0x1
        push 0x0
        lea eax, [ebp + {a('s_regkey')}]
        push eax
        push 0x80000001
        call {imp('RegOpenKeyExA')}
        test eax, eax
        jnz dm_on
        mov dword ptr [ebp + {D.sym['g_mbi'] + 4:#x}], 0x0
        mov dword ptr [ebp + {D.sym['g_mbi'] + 8:#x}], 0x8
        lea eax, [ebp + {D.sym['g_mbi'] + 8:#x}]
        push eax
        lea eax, [ebp + {D.sym['g_mbi'] + 12:#x}]
        push eax
        lea eax, [ebp + {D.sym['g_mbi'] + 4:#x}]
        push eax
        push 0x0
        lea eax, [ebp + {a('s_regval')}]
        push eax
        push dword ptr [ebp + {a('g_mbi')}]
        call {imp('RegQueryValueExA')}
        push eax
        push dword ptr [ebp + {a('g_mbi')}]
        call {imp('RegCloseKey')}
        pop eax
        test eax, eax
        jnz dm_on
        cmp dword ptr [ebp + {D.sym['g_mbi'] + 4:#x}], 0x4
        jne dm_on
        cmp dword ptr [ebp + {D.sym['g_mbi'] + 12:#x}], 0x0
        je dm_done
    dm_on:
        lea eax, [ebp + tproc]
        push eax
        push 0x64
        push 0x0
        push 0x0
        call {imp('SetTimer')}
        lea eax, [ebp + veh]
        push eax
        push 0x1
        call {imp('AddVectoredExceptionHandler')}
        call hook1
    dm_done:
        popal
    dm_ok:
        mov eax, 0x1
        ret 0xc

    hook1:
        lea eax, [ebp + {a('s_aowe')}]
        push eax
        call {imp('GetModuleHandleA')}
        test eax, eax
        jz h1_r
        lea edi, [eax + {EP_RANDOM_RVA:#x}]
        cmp dword ptr [edi], 0xf28b5653
        jne h1_r
        cmp word ptr [edi + 0x4], 0xd88b
        jne h1_r
        lea eax, [edi + 0x6]
        mov {v('g_rback')}, eax
        lea eax, [ebp + {a('g_old')}]
        push eax
        push 0x40
        push 0x6
        push edi
        call {imp('VirtualProtect')}
        test eax, eax
        jz h1_r
        lea eax, [ebp + h_random]
        sub eax, edi
        sub eax, 0x5
        mov byte ptr [edi], 0xe9
        mov dword ptr [edi + 0x1], eax
        mov byte ptr [edi + 0x5], 0x90
        lea eax, [ebp + {a('g_old')}]
        push eax
        push {v('g_old')}
        push 0x6
        push edi
        call {imp('VirtualProtect')}
    h1_r:
        ret

    hook2:
        mov {v('g_h2')}, 0x1
        mov eax, 0x1
        xchg eax, {v('g_inveh')}
        test eax, eax
        jnz h2_hello
        call wopen
        call wclose
        mov {v('g_inveh')}, 0x0
    h2_hello:
        lea eax, [ebp + {a('s_net')}]
        push eax
        call {imp('GetModuleHandleA')}
        test eax, eax
        jz h2_no
        lea edi, [eax + {NET_SYNC_RVA:#x}]
        cmp dword ptr [edi], 0xfff863e8
        jne h2_r
        cmp byte ptr [edi + 0x4], 0xff
        jne h2_r
        lea eax, [edi - 0x798]
        mov {v('g_sorig')}, eax
        lea eax, [ebp + {a('g_old')}]
        push eax
        push 0x40
        push 0x5
        push edi
        call {imp('VirtualProtect')}
        test eax, eax
        jz h2_r
        lea eax, [ebp + h_sync]
        sub eax, edi
        sub eax, 0x5
        mov dword ptr [edi + 0x1], eax
        lea eax, [ebp + {a('g_old')}]
        push eax
        push {v('g_old')}
        push 0x5
        push edi
        call {imp('VirtualProtect')}
        ret
    h2_no:
        mov {v('g_h2')}, 0x0
    h2_r:
        ret

    h_random:
        push ebp
        push ecx
        push edi
        call {GD:#x}
        cmp {v('g_h2')}, 0x0
        jne hr_1
        pushal
        call hook2
        popal
    hr_1:
        test eax, eax
        jz hr_2
        mov ecx, {v('g_rpos')}
        inc {v('g_rpos')}
        and ecx, {RING_N - 1:#x}
        shl ecx, 0x4
        lea edi, [ebp + ecx + {a('g_ring')}]
        mov dword ptr [edi], 0x1
        mov ecx, dword ptr [esp + 0xc]
        mov dword ptr [edi + 0x4], ecx
        mov dword ptr [edi + 0x8], edx
        mov ecx, dword ptr [eax + 0x230]
        mov dword ptr [edi + 0xc], ecx
    hr_2:
        pop edi
        pop ecx
        xchg ebx, dword ptr [esp]
        push esi
        mov esi, {v('g_rback')}
        mov ebp, ebx
        mov ebx, eax
        push esi
        mov esi, edx
        ret

    h_sync:
        push ebp
        call {GD:#x}
        call {v('g_sorig')}
        pushal
        mov edx, dword ptr [esi + 0x10]
        mov {v('g_local')}, eax
        mov {v('g_remote')}, edx
        mov ecx, {v('g_rpos')}
        inc {v('g_rpos')}
        and ecx, {RING_N - 1:#x}
        shl ecx, 0x4
        lea edi, [ebp + ecx + {a('g_ring')}]
        mov dword ptr [edi], 0x2
        mov dword ptr [edi + 0x4], edx
        mov dword ptr [edi + 0x8], eax
        mov dword ptr [edi + 0xc], 0x0
        cmp eax, edx
        je hs_ok
        cmp {v('g_dumps')}, 0x8
        jae hs_ok
        inc {v('g_dumps')}
        call oosdump
    hs_ok:
        popal
        pop ebp
        ret

    wopen:
        cmp {v('g_h')}, 0x0
        jne wo_r
        push 0x0
        push 0x80
        push 0x4
        push 0x0
        push 0x3
        push 0x40000000
        lea eax, [ebp + {a('g_path')}]
        push eax
        call {imp('CreateFileA')}
        cmp eax, -0x1
        je wo_r
        mov {v('g_h')}, eax
        cmp {v('g_hdr')}, 0x0
        jne wo_end
        mov {v('g_hdr')}, 0x1
        push 0x0
        push eax
        call {imp('GetFileSize')}
        cmp eax, 0x400000
        jb wo_h
        push 0x0
        push 0x0
        push 0x0
        push {v('g_h')}
        call {imp('SetFilePointer')}
        push {v('g_h')}
        call {imp('SetEndOfFile')}
    wo_h:
        call wend
        lea eax, [ebp + {a('g_st')}]
        push eax
        call {imp('GetLocalTime')}
        movzx eax, word ptr [ebp + {D.sym['g_st'] + 12:#x}]
        push eax
        movzx eax, word ptr [ebp + {D.sym['g_st'] + 10:#x}]
        push eax
        movzx eax, word ptr [ebp + {D.sym['g_st'] + 8:#x}]
        push eax
        movzx eax, word ptr [ebp + {D.sym['g_st'] + 6:#x}]
        push eax
        movzx eax, word ptr [ebp + {D.sym['g_st'] + 2:#x}]
        push eax
        movzx eax, word ptr [ebp + {D.sym['g_st']:#x}]
        push eax
        lea eax, [ebp + {a('g_exe')}]
        push eax
        lea eax, [ebp + {a('f_hdr')}]
        push eax
        lea eax, [ebp + {a('g_line')}]
        push eax
        call {imp('wsprintfA')}
        add esp, 0x24
        call wflush
        ret
    wo_end:
        call wend
    wo_r:
        ret
    wend:
        push 0x2
        push 0x0
        push 0x0
        push {v('g_h')}
        call {imp('SetFilePointer')}
        ret
    wflush:
        cmp {v('g_h')}, 0x0
        je wf_r
        lea eax, [ebp + {a('g_line')}]
        push eax
        call {imp('lstrlenA')}
        push 0x0
        lea ecx, [ebp + {a('g_wr')}]
        push ecx
        push eax
        lea eax, [ebp + {a('g_line')}]
        push eax
        push {v('g_h')}
        call {imp('WriteFile')}
    wf_r:
        lea eax, [ebp + {a('g_line')}]
        mov {v('g_lp')}, eax
        mov byte ptr [eax], 0x0
        ret
    wclose:
        cmp {v('g_h')}, 0x0
        je wc_r
        push {v('g_h')}
        call {imp('CloseHandle')}
        mov {v('g_h')}, 0x0
    wc_r:
        ret

    tstamp:
        lea eax, [ebp + {a('g_st')}]
        push eax
        call {imp('GetLocalTime')}
        movzx eax, word ptr [ebp + {D.sym['g_st'] + 12:#x}]
        push eax
        movzx eax, word ptr [ebp + {D.sym['g_st'] + 10:#x}]
        push eax
        movzx eax, word ptr [ebp + {D.sym['g_st'] + 8:#x}]
        push eax
        lea eax, [ebp + {a('f_ts')}]
        push eax
        push {v('g_lp')}
        call {imp('wsprintfA')}
        add esp, 0x14
        add {v('g_lp')}, eax
        ret

    fmtaddr:
        push ebx
        push esi
        mov ebx, eax
        push 0x1c
        lea eax, [ebp + {a('g_mbi')}]
        push eax
        push ebx
        call {imp('VirtualQuery')}
        test eax, eax
        jz fa_unk
        mov esi, dword ptr [ebp + {D.sym['g_mbi'] + 4:#x}]
        test esi, esi
        jz fa_unk
        cmp dword ptr [ebp + {D.sym['g_mbi'] + 0x18:#x}], 0x1000000
        jne fa_unk
        cmp esi, {v('g_cbase')}
        je fa_have
        push 0x104
        lea eax, [ebp + {a('g_mpath')}]
        push eax
        push esi
        call {imp('GetModuleFileNameA')}
        test eax, eax
        jz fa_unk
        mov {v('g_cbase')}, esi
        lea eax, [ebp + {a('g_mpath')}]
        mov edx, eax
    fa_l:
        mov cl, byte ptr [eax]
        test cl, cl
        jz fa_d
        inc eax
        cmp cl, 0x5c
        jne fa_l
        mov edx, eax
        jmp fa_l
    fa_d:
        mov {v('g_cname')}, edx
    fa_have:
        mov eax, {v('g_cname')}
        mov edx, ebx
        sub edx, esi
        jmp fa_r
    fa_unk:
        lea eax, [ebp + {a('s_unk')}]
        mov edx, ebx
    fa_r:
        pop esi
        pop ebx
        ret

    stackline:
        push ebx
        push esi
        push edi
        mov esi, eax
        mov eax, {v('g_sln')}
        shl eax, 0x2
        push eax
        push esi
        call {imp('IsBadReadPtr')}
        test eax, eax
        jnz sl_r
        lea eax, [ebp + {a('f_stk0')}]
        push eax
        push {v('g_lp')}
        call {imp('wsprintfA')}
        add esp, 0x8
        add {v('g_lp')}, eax
        mov edi, {v('g_sln')}
        xor ebx, ebx
    sl_l:
        mov eax, dword ptr [esi]
        add esi, 0x4
        cmp eax, 0x10000
        jb sl_n
        push eax
        push 0x1c
        lea ecx, [ebp + {a('g_mbi')}]
        push ecx
        push eax
        call {imp('VirtualQuery')}
        test eax, eax
        pop eax
        jz sl_n
        cmp dword ptr [ebp + {D.sym['g_mbi'] + 0x18:#x}], 0x1000000
        jne sl_n
        cmp dword ptr [ebp + {D.sym['g_mbi'] + 0x10:#x}], 0x1000
        jne sl_n
        test byte ptr [ebp + {D.sym['g_mbi'] + 0x14:#x}], 0xf0
        jz sl_n
        call fmtaddr
        push edx
        push eax
        lea eax, [ebp + {a('f_stk')}]
        push eax
        push {v('g_lp')}
        call {imp('wsprintfA')}
        add esp, 0x10
        add {v('g_lp')}, eax
        inc ebx
        cmp ebx, {v('g_slm')}
        jae sl_e
    sl_n:
        dec edi
        jnz sl_l
    sl_e:
        lea eax, [ebp + {a('s_crlf')}]
        push eax
        push {v('g_lp')}
        call {imp('wsprintfA')}
        add esp, 0x8
        add {v('g_lp')}, eax
    sl_r:
        pop edi
        pop esi
        pop ebx
        ret

    veh:
        push ebp
        push ebx
        push esi
        push edi
        call {GD:#x}
        mov eax, 0x1
        xchg eax, {v('g_inveh')}
        test eax, eax
        jnz v_out
        mov esi, dword ptr [esp + 0x14]
        mov ebx, dword ptr [esi]
        mov edi, dword ptr [esi + 0x4]
        mov eax, dword ptr [ebx]
        cmp eax, 0xeedfade
        je v_go
        cmp eax, 0xc0000000
        jb v_done
    v_go:
        mov ecx, dword ptr [ebx + 0xc]
        cmp eax, 0xeedfade
        jne v_dd
        mov ecx, dword ptr [ebx + 0x14]
    v_dd:
        cmp eax, {v('g_lastcode')}
        jne v_new
        cmp ecx, {v('g_lastaddr')}
        jne v_new
        inc {v('g_rep')}
        jmp v_done
    v_new:
        mov {v('g_lastcode')}, eax
        mov {v('g_lastaddr')}, ecx
        cmp {v('g_nlog')}, {MAX_LOG:#x}
        ja v_done
        call wopen
        cmp {v('g_h')}, 0x0
        je v_done
        lea eax, [ebp + {a('g_line')}]
        mov {v('g_lp')}, eax
        cmp {v('g_rep')}, 0x0
        je v_norep
        push {v('g_rep')}
        lea eax, [ebp + {a('f_rep')}]
        push eax
        push {v('g_lp')}
        call {imp('wsprintfA')}
        add esp, 0xc
        add {v('g_lp')}, eax
        mov {v('g_rep')}, 0x0
    v_norep:
        inc {v('g_nlog')}
        cmp {v('g_nlog')}, {MAX_LOG:#x}
        jbe v_fmt
        lea eax, [ebp + {a('f_max')}]
        push eax
        push {v('g_lp')}
        call {imp('wsprintfA')}
        add esp, 0x8
        call wflush
        call wclose
        jmp v_done
    v_fmt:
        call tstamp
        cmp dword ptr [ebx], 0xeedfade
        jne v_nat
        mov eax, dword ptr [ebx + 0x14]
        call fmtaddr
        push edx
        push eax
        lea ecx, [ebp + {a('s_none')}]
        lea edx, [ebp + {a('s_unk')}]
        mov eax, dword ptr [ebx + 0x18]
        push eax
        push ecx
        push edx
        push 0x8
        push eax
        call {imp('IsBadReadPtr')}
        test eax, eax
        pop edx
        pop ecx
        pop eax
        jnz v_d2
        push eax
        mov eax, dword ptr [eax + 0x4]
        test eax, eax
        jz v_d1
        push ecx
        push edx
        push eax
        push 0x1
        push eax
        call {imp('IsBadReadPtr')}
        test eax, eax
        pop eax
        pop edx
        pop ecx
        jnz v_d1
        mov ecx, eax
    v_d1:
        pop eax
        mov eax, dword ptr [eax]
        sub eax, 0x20
        push ecx
        push eax
        push 0x4
        push eax
        call {imp('IsBadReadPtr')}
        test eax, eax
        pop eax
        pop ecx
        lea edx, [ebp + {a('s_unk')}]
        jnz v_d2
        mov eax, dword ptr [eax]
        push ecx
        push eax
        push 0x40
        push eax
        call {imp('IsBadReadPtr')}
        test eax, eax
        pop eax
        pop ecx
        lea edx, [ebp + {a('s_unk')}]
        jnz v_d2
        movzx edx, byte ptr [eax]
        cmp edx, 0x3c
        ja v_d3
        lea esi, [eax + 0x1]
        push edi
        lea edi, [ebp + {a('g_cls')}]
        push ecx
        mov ecx, edx
        rep movsb
        mov byte ptr [edi], 0x0
        pop ecx
        pop edi
        lea edx, [ebp + {a('g_cls')}]
        jmp v_d2
    v_d3:
        lea edx, [ebp + {a('s_unk')}]
    v_d2:
        push ecx
        push edx
        lea eax, [ebp + {a('s_exc')}]
        push eax
        push edx
        call {imp('lstrcmpA')}
        pop edx
        pop ecx
        test eax, eax
        mov eax, edx
        jnz v_t1
        cmp byte ptr [ecx], 0x0
        je v_t1
        mov eax, ecx
    v_t1:
        cmp byte ptr [edx], 0x3f
        jne v_t2
        lea eax, [ebp + {a('s_err')}]
    v_t2:
        push ecx
        push edx
        mov edx, {v('g_lastcode')}
        mov ecx, {v('g_lastaddr')}
        call arm
        pop edx
        pop ecx
        push ecx
        push edx
        lea eax, [ebp + {a('f_delphi')}]
        push eax
        push {v('g_lp')}
        call {imp('wsprintfA')}
        add esp, 0x18
        add {v('g_lp')}, eax
        jmp v_stk
    v_nat:
        mov eax, dword ptr [ebx]
        lea edx, [ebp + {a('s_av')}]
        cmp eax, 0xc0000005
        je v_n1
        lea edx, [ebp + {a('s_div')}]
        cmp eax, 0xc0000094
        je v_n1
        lea edx, [ebp + {a('s_so')}]
        cmp eax, 0xc00000fd
        je v_n1
        lea edx, [ebp + {a('s_ill')}]
        cmp eax, 0xc000001d
        je v_n1
        push eax
        lea eax, [ebp + {a('f_xcode')}]
        push eax
        lea eax, [ebp + {a('g_cls')}]
        push eax
        call {imp('wsprintfA')}
        add esp, 0xc
        lea edx, [ebp + {a('g_cls')}]
    v_n1:
        mov eax, edx
        mov edx, {v('g_lastcode')}
        mov ecx, {v('g_lastaddr')}
        call arm
        mov eax, dword ptr [ebx + 0xc]
        call fmtaddr
        push edx
        push eax
        push dword ptr [ebx]
        lea eax, [ebp + {a('f_native')}]
        push eax
        push {v('g_lp')}
        call {imp('wsprintfA')}
        add esp, 0x14
        add {v('g_lp')}, eax
        cmp dword ptr [ebx], 0xc0000005
        jne v_regs
        cmp dword ptr [ebx + 0x10], 0x2
        jb v_regs
        lea eax, [ebp + {a('s_read')}]
        mov ecx, dword ptr [ebx + 0x14]
        test ecx, ecx
        jz v_av
        lea eax, [ebp + {a('s_write')}]
        cmp ecx, 0x1
        je v_av
        lea eax, [ebp + {a('s_exec')}]
    v_av:
        push dword ptr [ebx + 0x18]
        push eax
        lea eax, [ebp + {a('f_av')}]
        push eax
        push {v('g_lp')}
        call {imp('wsprintfA')}
        add esp, 0x10
        add {v('g_lp')}, eax
    v_regs:
        push dword ptr [edi + 0xc4]
        push dword ptr [edi + 0xb4]
        push dword ptr [edi + 0x9c]
        push dword ptr [edi + 0xa0]
        push dword ptr [edi + 0xa8]
        push dword ptr [edi + 0xac]
        push dword ptr [edi + 0xa4]
        push dword ptr [edi + 0xb0]
        lea eax, [ebp + {a('f_regs')}]
        push eax
        push {v('g_lp')}
        call {imp('wsprintfA')}
        add esp, 0x28
        add {v('g_lp')}, eax
    v_stk:
        mov eax, dword ptr [edi + 0xc4]
        call stackline
        lea eax, [ebp + {a('g_ref')}]
        push eax
        lea eax, [ebp + {a('f_ref')}]
        push eax
        push {v('g_lp')}
        call {imp('wsprintfA')}
        add esp, 0xc
        add {v('g_lp')}, eax
        call wflush
        call wclose
    v_done:
        mov {v('g_inveh')}, 0x0
    v_out:
        pop edi
        pop esi
        pop ebx
        pop ebp
        xor eax, eax
        ret 0x4

    oosdump:
        mov eax, 0x1
        xchg eax, {v('g_inveh')}
        test eax, eax
        jnz od_r
        call wopen
        cmp {v('g_h')}, 0x0
        je od_x
        lea eax, [ebp + {a('g_line')}]
        mov {v('g_lp')}, eax
        lea eax, [ebp + {a('s_oos')}]
        mov edx, {v('g_dumps')}
        add edx, 0x50000
        xor ecx, ecx
        call arm
        call tstamp
        mov ebx, {v('g_rpos')}
        mov esi, ebx
        sub esi, {RING_N:#x}
        jae od_1
        xor esi, esi
    od_1:
        mov eax, ebx
        sub eax, esi
        push eax
        push ebx
        push {v('g_remote')}
        push {v('g_local')}
        lea eax, [ebp + {a('g_ref')}]
        push eax
        lea eax, [ebp + {a('f_oos')}]
        push eax
        push {v('g_lp')}
        call {imp('wsprintfA')}
        add esp, 0x1c
        call wflush
    od_l:
        cmp esi, ebx
        jae od_e
        mov ecx, esi
        and ecx, {RING_N - 1:#x}
        shl ecx, 0x4
        lea edi, [ebp + ecx + {a('g_ring')}]
        cmp dword ptr [edi], 0x1
        jne od_s
        mov eax, dword ptr [edi + 0x4]
        call fmtaddr
        push edx
        push eax
        push dword ptr [edi + 0x8]
        push dword ptr [edi + 0xc]
        push esi
        lea eax, [ebp + {a('f_r')}]
        push eax
        push {v('g_lp')}
        call {imp('wsprintfA')}
        add esp, 0x1c
        jmp od_w
    od_s:
        lea eax, [ebp + {a('s_ok')}]
        mov ecx, dword ptr [edi + 0x4]
        cmp ecx, dword ptr [edi + 0x8]
        je od_s1
        lea eax, [ebp + {a('s_bad')}]
    od_s1:
        push eax
        push dword ptr [edi + 0x4]
        push dword ptr [edi + 0x8]
        push esi
        lea eax, [ebp + {a('f_s')}]
        push eax
        push {v('g_lp')}
        call {imp('wsprintfA')}
        add esp, 0x18
    od_w:
        call wflush
        inc esi
        jmp od_l
    od_e:
        lea eax, [ebp + {a('f_end')}]
        push eax
        push {v('g_lp')}
        call {imp('wsprintfA')}
        add esp, 0x8
        call wflush
        call wclose
    od_x:
        mov {v('g_inveh')}, 0x0
    od_r:
        ret

    arm:
        pushal
        mov esi, eax
        cmp {v('g_saving')}, 0x0
        jne arm_r
        cmp {v('g_pend')}, 0x0
        jne arm_r
        lea edi, [ebp + {a('g_sig')}]
        mov ebx, {v('g_nsig')}
    arm_l:
        test ebx, ebx
        jz arm_new
        cmp dword ptr [edi], edx
        jne arm_n
        cmp dword ptr [edi + 0x4], ecx
        jne arm_n
        lea esi, [edi + 0x8]
        lea edi, [ebp + {a('g_ref')}]
        mov ecx, 0x18
        rep movsb
        jmp arm_r
    arm_n:
        add edi, 0x20
        dec ebx
        jmp arm_l
    arm_new:
        mov dword ptr [edi], edx
        mov dword ptr [edi + 0x4], ecx
        cmp {v('g_nsig')}, {NSIG:#x}
        jae arm_f
        inc {v('g_nsig')}
    arm_f:
        lea eax, [ebp + {a('g_st')}]
        push eax
        call {imp('GetLocalTime')}
        inc {v('g_refn')}
        call {imp('GetCurrentProcessId')}
        imul ebx, eax, 0x7
        call {imp('GetTickCount')}
        add ebx, eax
        imul eax, {v('g_refn')}, 0x25
        add eax, ebx
        xor edx, edx
        mov ecx, 0x3e8
        div ecx
        push edx
        movzx eax, word ptr [ebp + {D.sym['g_st'] + 12:#x}]
        push eax
        movzx eax, word ptr [ebp + {D.sym['g_st'] + 10:#x}]
        push eax
        movzx eax, word ptr [ebp + {D.sym['g_st'] + 8:#x}]
        push eax
        movzx eax, word ptr [ebp + {D.sym['g_st'] + 6:#x}]
        push eax
        movzx eax, word ptr [ebp + {D.sym['g_st'] + 2:#x}]
        push eax
        movzx eax, word ptr [ebp + {D.sym['g_st']:#x}]
        xor edx, edx
        mov ecx, 0x64
        div ecx
        push edx
        lea eax, [ebp + {a('f_mkref')}]
        push eax
        lea eax, [ebp + {a('g_ref')}]
        push eax
        call {imp('wsprintfA')}
        add esp, 0x24
        push esi
        lea esi, [ebp + {a('g_ref')}]
        add edi, 0x8
        mov ecx, 0x18
        rep movsb
        pop esi
        lea edi, [ebp + {a('g_type')}]
        mov ecx, 0x28
    arm_t:
        mov al, byte ptr [esi]
        inc esi
        test al, al
        jz arm_t2
        cmp al, 0x20
        jb arm_tu
        cmp al, 0x5c
        je arm_tu
        cmp al, 0x2f
        je arm_tu
        cmp al, 0x3a
        je arm_tu
        cmp al, 0x2a
        je arm_tu
        cmp al, 0x3f
        je arm_tu
        cmp al, 0x22
        je arm_tu
        cmp al, 0x3c
        je arm_tu
        cmp al, 0x3e
        je arm_tu
        cmp al, 0x7c
        je arm_tu
        cmp al, 0x25
        jne arm_ts
    arm_tu:
        mov al, 0x5f
    arm_ts:
        mov byte ptr [edi], al
        inc edi
        dec ecx
        jnz arm_t
    arm_t2:
        lea eax, [ebp + {a('g_type')}]
    arm_t3:
        cmp edi, eax
        jbe arm_t4
        mov cl, byte ptr [edi - 0x1]
        cmp cl, 0x20
        je arm_t5
        cmp cl, 0x2e
        jne arm_t6
    arm_t5:
        dec edi
        jmp arm_t3
    arm_t4:
        mov dword ptr [edi], 0x6f727245
        mov byte ptr [edi + 0x4], 0x72
        add edi, 0x5
    arm_t6:
        mov byte ptr [edi], 0x0
        cmp {v('g_nsave')}, {MAX_SAVES:#x}
        jae arm_r
        mov {v('g_pend')}, 0x1
    arm_r:
        popal
        ret

    note:
        mov eax, 0x1
        xchg eax, {v('g_inveh')}
        test eax, eax
        jnz nt_r
        push edx
        call wopen
        pop edx
        cmp {v('g_h')}, 0x0
        je nt_x
        lea eax, [ebp + {a('g_line')}]
        mov {v('g_lp')}, eax
        push edx
        call tstamp
        pop edx
        lea eax, [ebp + {D.sym['g_sname'] + 8:#x}]
        push eax
        lea eax, [ebp + {a('g_ref')}]
        push eax
        push edx
        push {v('g_lp')}
        call {imp('wsprintfA')}
        add esp, 0x10
        call wflush
        call wclose
    nt_x:
        mov {v('g_inveh')}, 0x0
    nt_r:
        ret

    tproc:
        pushal
        call {GD:#x}
        call fztick
        cmp {v('g_pend')}, 0x0
        je tp_r
        mov eax, 0x1
        xchg eax, {v('g_inveh')}
        test eax, eax
        jnz tp_r
        mov {v('g_pend')}, 0x0
        mov al, byte ptr [ebp + {D.sym['g_exe'] + 3:#x}]
        or al, 0x20
        cmp al, 0x64
        je tp_nogame
        lea eax, [ebp + {a('s_aowe')}]
        push eax
        call {imp('GetModuleHandleA')}
        test eax, eax
        jz tp_nogame
        mov esi, eax
        cmp dword ptr [esi + {MAP_RVA:#x}], 0x0
        je tp_nogame
        mov ebx, dword ptr [esi + {ENGINE_RVA:#x}]
        test ebx, ebx
        jz tp_nogame
        cmp word ptr [esi + {HANDLEANY_RVA:#x}], 0x25ff
        jne tp_nogame
        cmp word ptr [esi + {DONEEXCEPT_RVA:#x}], 0x25ff
        jne tp_nogame
        xor ecx, ecx
        xor edx, edx
        cmp byte ptr [esi + {VER_RVA + 2:#x}], 0x68
        jne tp_v
        cmp byte ptr [esi + {VER_RVA:#x}], 0xb1
        jne tp_v
        movzx ecx, byte ptr [esi + {VER_RVA + 1:#x}]
        mov edx, dword ptr [esi + {VER_RVA + 3:#x}]
    tp_v:
        lea eax, [ebp + {a('g_ref')}]
        push eax
        lea eax, [ebp + {a('g_type')}]
        push eax
        push edx
        push ecx
        lea eax, [ebp + {a('g_dir')}]
        push eax
        lea eax, [ebp + {a('f_save')}]
        push eax
        lea eax, [ebp + {D.sym['g_sname'] + 8:#x}]
        push eax
        call {imp('wsprintfA')}
        add esp, 0x1c
        mov dword ptr [ebp + {D.sym['g_sname'] + 4:#x}], eax
        mov dword ptr [ebp + {D.sym['g_sname']:#x}], 0xffffffff
        lea eax, [esi + {HANDLEANY_RVA:#x}]
        lea ecx, [ebp + tp_exc]
        sub eax, ecx
        sub eax, 0x5
        mov dword ptr [ecx + 0x1], eax
        lea eax, [esi + {DONEEXCEPT_RVA:#x}]
        mov {v('g_done')}, eax
        mov {v('g_sok')}, 0x0
        mov {v('g_saving')}, 0x1
        mov {v('g_inveh')}, 0x0
        xor eax, eax
        push ebp
        lea ecx, [ebp + tp_exc]
        push ecx
        push dword ptr fs:[eax]
        mov dword ptr fs:[eax], esp
        push 0x0
        push 0x0
        lea edx, [ebp + {D.sym['g_sname'] + 8:#x}]
        mov eax, ebx
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0xac]
        mov {v('g_sok')}, 0x1
        inc {v('g_nsave')}
        xor eax, eax
        pop edx
        pop ecx
        pop ecx
        mov dword ptr fs:[eax], edx
        jmp tp_after
    tp_exc:
        .byte 0xe9, 0x0, 0x0, 0x0, 0x0
        call {v('g_done')}
    tp_after:
        mov {v('g_saving')}, 0x0
        lea edx, [ebp + {a('f_saved')}]
        cmp {v('g_sok')}, 0x0
        jne tp_log
        lea edx, [ebp + {a('f_sfail')}]
        jmp tp_log
    tp_nogame:
        mov {v('g_inveh')}, 0x0
        lea edx, [ebp + {a('f_nosave')}]
    tp_log:
        call note
    tp_r:
        popal
        ret 0x10

    testdump:
        pushal
        call {GD:#x}
        mov {v('g_local')}, 0x11111111
        mov {v('g_remote')}, 0x22222222
        call oosdump
        popal
        xor eax, eax
        ret 0x4
{FZ}
        mov eax, dllmain
        mov eax, testdump
        mov eax, testfreeze
        mov eax, rs_cb
    """


def build_imports(rva):
    nd = len(IMPORTS)
    desc_sz = 20 * (nd + 1)
    sizes = [4 * (len(f) + 1) for _d, f in IMPORTS]
    ilt_off = desc_sz
    iat_off = ilt_off + sum(sizes)
    names_off = iat_off + sum(sizes)
    names, name_rva = bytearray(), {}
    for dll, funcs in IMPORTS:
        name_rva[dll] = rva + names_off + len(names); names += dll.encode() + b"\0"
        if len(names) % 2: names += b"\0"
        for f in funcs:
            name_rva[(dll, f)] = rva + names_off + len(names)
            names += struct.pack("<H", 0) + f.encode() + b"\0"
            if len(names) % 2: names += b"\0"
    b = bytearray(names_off) + names
    iat_va = {}
    o_ilt, o_iat = ilt_off, iat_off
    for i, (dll, funcs) in enumerate(IMPORTS):
        struct.pack_into("<IIIII", b, 20 * i, rva + o_ilt, 0, 0, name_rva[dll], rva + o_iat)
        for j, f in enumerate(funcs):
            struct.pack_into("<I", b, o_ilt + 4 * j, name_rva[(dll, f)])
            struct.pack_into("<I", b, o_iat + 4 * j, name_rva[(dll, f)])
            iat_va[f] = BASE + rva + o_iat + 4 * j
        o_ilt += 4 * (len(funcs) + 1); o_iat += 4 * (len(funcs) + 1)
    return bytes(b), iat_va, rva, desc_sz, rva + iat_off, sum(sizes)


def build_exports(rva, funcs):
    funcs = sorted(funcs)
    n = len(funcs)
    name = b"AoWxLog.dll\0"
    o_funcs = 40; o_names = o_funcs + 4 * n; o_ords = o_names + 4 * n; o_dll = o_ords + 2 * n
    strs, name_off = bytearray(name), []
    for fn, _r in funcs:
        name_off.append(o_dll + len(strs)); strs += fn.encode() + b"\0"
    b = bytearray(o_dll) + strs
    struct.pack_into("<IIHHIIIIIII", b, 0, 0, 0, 0, 0, rva + o_dll, 1, n, n, rva + o_funcs, rva + o_names, rva + o_ords)
    for i, (fn, fr) in enumerate(funcs):
        struct.pack_into("<I", b, o_funcs + 4 * i, fr)
        struct.pack_into("<I", b, o_names + 4 * i, rva + name_off[i])
        struct.pack_into("<H", b, o_ords + 2 * i, i)
    return bytes(b)


def build():
    import sky_clouds_overlay_asm as OV
    D = build_data(BASE + SEC_RVA)
    while len(D.b) % 16:
        D.b.append(0)
    imp_rva = SEC_RVA + len(D.b)
    ib, IAT, idir, isz, iat_rva, iat_sz = build_imports(imp_rva)
    body = bytearray(D.b) + ib
    while len(body) % 16:
        body.append(0)
    code_rva = SEC_RVA + len(body)
    code_va = BASE + code_rva
    gd = code_va
    prolog = bytearray(0x10)
    prolog[0:12] = b"\xe8\x00\x00\x00\x00\x5d\x81\xed" + struct.pack("<I", gd + 5)   # call $+5 ; pop ebp ; sub ebp, imm
    prolog[12] = 0xC3
    code = OV.asm(asm_text(D, IAT, gd), code_va + 0x10)
    tail = code[-20:]
    assert all(tail[5 * k] == 0xB8 for k in range(4)), tail.hex()
    main_va, test_va, tfz_va, rscb_va = (struct.unpack_from("<I", tail, 1 + 5 * k)[0] for k in range(4))
    code = code[:-20]
    body += prolog + code
    while len(body) % 16:
        body.append(0)
    exp_rva = SEC_RVA + len(body)
    eb = build_exports(exp_rva, [("TestDump", test_va - BASE), ("TestFreeze", tfz_va - BASE)])
    body += eb
    sec_vs = len(body)
    raw_sz = (sec_vs + 0x1FF) & ~0x1FF
    reloc_rva = (SEC_RVA + sec_vs + 0xFFF) & ~0xFFF
    reloc = struct.pack("<IIHH", SEC_RVA, 12, 0, 0)
    size_of_image = reloc_rva + 0x1000
    h = bytearray(0x400)
    h[0:2] = b"MZ"; struct.pack_into("<I", h, 0x3C, 0x40)
    h[0x40:0x44] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", h, 0x44, 0x14C, 2, 0, 0, 0, 0xE0, 0x2102)
    o = 0x58
    struct.pack_into("<HBBIIIIII", h, o, 0x10B, 6, 0, raw_sz, 0x200, 0, main_va - BASE, SEC_RVA, SEC_RVA)
    struct.pack_into("<IIIHHHHHHIIIIHHIIIIII", h, o + 28, BASE, 0x1000, 0x200, 4, 0, 0, 0, 4, 0, 0,
                     size_of_image, 0x400, 0, 2, 0, 0x100000, 0x1000, 0x100000, 0x1000, 0, 16)
    dd = o + 96
    struct.pack_into("<II", h, dd + 0 * 8, exp_rva, len(eb))
    struct.pack_into("<II", h, dd + 1 * 8, idir, isz)
    struct.pack_into("<II", h, dd + 5 * 8, reloc_rva, len(reloc))
    struct.pack_into("<II", h, dd + 12 * 8, iat_rva, iat_sz)
    so = o + 0xE0
    h[so:so + 8] = b".text\0\0\0"
    struct.pack_into("<IIIIIIHHI", h, so + 8, sec_vs, SEC_RVA, raw_sz, 0x400, 0, 0, 0, 0, 0xE0000060)
    h[so + 40:so + 48] = b".reloc\0\0"
    struct.pack_into("<IIIIIIHHI", h, so + 48, len(reloc), reloc_rva, 0x200, 0x400 + raw_sz, 0, 0, 0, 0, 0x42000040)
    img = bytes(h) + bytes(body) + bytes(raw_sz - len(body)) + reloc + bytes(0x200 - len(reloc))
    return img, dict(code_len=len(code), main=main_va, test=test_va, tfz=tfz_va, rscb=rscb_va, sym=D.sym, code_va=code_va, iat=IAT)


def main():
    img, info = build()
    print("AoWxLog.dll %d B | code %d B | DllMain %#x | TestDump %#x" % (len(img), info["code_len"], info["main"], info["test"]))
    if "--check" in sys.argv:
        return 0
    cur = open(OUT, "rb").read() if os.path.exists(OUT) else None
    if cur == img:
        print("already up to date:", OUT); return 0
    open(OUT, "wb").write(img)
    print("written", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""LAN out-of-sync DIAGNOSTIC patch (AoWEPACK.dll) - record-only, revertible.

Background (2026-08-07 investigation): the MP out-of-sync check is literally a
synced-RNG-state compare.  NetworkE.TSyncTE.Execute (Network.dpl 0x558043E4)
compares the sync value carried in the token against the local executer's
GetSyncValue -> AoWE.TPlayerControl.GetSyncValue = [AoWHSMap+0x230], which is
exactly TAoWHSMap.Random's stored seed (Random @0x5577827C: RandSeed :=
[map+0x230]; RandInt; [map+0x230] := RandSeed).  So "out of sync" == the two
clients consumed different synced Random rolls.

Recruiting an independent party flows: TArmyHS.MapFieldMsgProc msg 0x110E ->
TArmy.IncommingNegotiateRequest (ACTING CLIENT ONLY - builds the join offer)
-> player accepts -> TNegotiateRequestEventLog.Accept -> TNegotiateTE token
-> ALL CLIENTS: TNegotiateTE.Execute -> Validate -> msg 0x110F ->
TArmy.IncommingNegotiateOffer -> re-checks GetJoinSelection/JoinAmount vs the
paid amount from the token, then joins + places units.  None of these call
Random directly, so the desync must come from a DIVERGENT BRANCH (join
succeeds on one client, silently bails on the other) whose side effects
(unit placement triggers etc.) then consume different Random rolls.

This patch records, in BSS page slack (RW to 0x558FAFFF, zeroed at load):

  SCRATCH @0x558FA980 (negotiate breadcrumbs):
    +0x00 dd  TNegotiateTE.Execute count          (token reached this client)
    +0x04 db  last TE player  +05 x  +06 y  +07 lvl
    +0x08 dd  last TE paid amount [TE+0x10]
    +0x0C db  accept[TE+0x2E]  +0D flags[TE+0x2D]  +0E mode[TE+0x24]
    +0x10 dd  IncommingNegotiateOffer count       (TE.Validate passed)
    +0x14 dd  offer paid  +18 db mode  +19 accept  +1A flags  +1B player
    +0x1C db  GetJoinSelection result (bitmask of joining units)
    +0x20 dd  JoinAmount computed on this client
    +0x24 dd  join-done count (reached BeginUpdate = units actually joined)
    +0x28 dd  amount-bail count (JoinAmount > paid -> silently no join)

  RING @0x558FAA00 (synced-RNG timeline):
    +0 dd count; +8: 128 entries x 8 bytes {caller/tag, seed-or-extra},
    index = count & 0x7F.  Every TAoWHSMap.Random call appends
    {caller retaddr, seed BEFORE the roll}.  The negotiate hooks append
    marker entries: 'NEGO' 0x4E45474F (TE executed, extra=paid),
    'OFFR' 0x4F464652 (offer reached, extra=paid), 'SELE' 0x53454C45
    (extra=selection), 'AMNT' 0x414D4E54 (extra=amount), 'JOIN' 0x4A4F494E.
    Diffing the two clients' rings (re_tools/desync_dump.py) shows the exact
    call where the streams diverge.

Hooks (all record-only; displaced instructions re-executed byte-for-byte):
  H1 0x5577827C TAoWHSMap.Random entry            (6 bytes displaced)
  H2 0x5572C62C TNegotiateTE.Execute entry        (6)
  H3 0x5578FBB4 TArmy.IncommingNegotiateOffer     (6)
  H4 0x5578FBF8 after GetJoinSelection            (6)
  H5 0x5578FC1B JoinAmount cmp/jg (replicated)    (9)
  H6 0x5578FC24 BeginUpdate = join-done           (7)

Cave @0x55811000 (file 0x110400, verified zeros; spring cave ends 0x55810500).
Dry-run default; --apply writes (backup AoWEPACK.dll.bak_desync_diag);
--revert restores all six sites + zeros the cave.
"""
import os
import shutil
import sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
TARGET = os.path.join(GAME, "AoWEPACK.dll")
BACKUP = TARGET + ".bak_desync_diag"

VA2FILE = 0x55700C00

SCRATCH = 0x558FA980
RING    = 0x558FAA00              # +0 count, +8 entries; 128*8 ends 0x558FAE08
RINGMASK = 0x7F

BEGINUPD = 0x55703284             # thunk EngineP!TEChangeNotifyNode.BeginUpdate

TAG_NEGO = 0x4E45474F
TAG_OFFR = 0x4F464652
TAG_SELE = 0x53454C45
TAG_AMNT = 0x414D4E54
TAG_JOIN = 0x4A4F494E

CAVE_BASE  = 0x55811000
CAVE_LIMIT = 0x55811200

# hook sites: (name, va, old bytes, cave label, nop-pad to len(old))
H_RANDOM  = 0x5577827C
H_NEGOEX  = 0x5572C62C
H_OFFER   = 0x5578FBB4
H_SEL     = 0x5578FBF8
H_AMT     = 0x5578FC1B
H_JOIN    = 0x5578FC24

OLD = {
    H_RANDOM: bytes.fromhex("53568BF28BD8"),        # push ebx;push esi;mov esi,edx;mov ebx,eax
    H_NEGOEX: bytes.fromhex("5383C4E08BD8"),        # push ebx;add esp,-20h;mov ebx,eax
    H_OFFER:  bytes.fromhex("558BEC83C4C0"),        # push ebp;mov ebp,esp;add esp,-40h
    H_SEL:    bytes.fromhex("8845FB8A55FB"),        # mov [ebp-5],al;mov dl,[ebp-5]
    H_AMT:    bytes.fromhex("3B43100F8F83040000"),  # cmp eax,[ebx+10h];jg 0x557900A7
    H_JOIN:   bytes.fromhex("8BC6E85936F7FF"),      # mov eax,esi;call BeginUpdate
}
AMT_BAIL  = 0x557900A7            # original jg target (amount too low -> no join)
AMT_FALL  = 0x5578FC24
JOIN_BACK = 0x5578FC2B


class Asm:
    def __init__(self, base):
        self.base = base; self.buf = bytearray(); self.labels = {}
        self.fix32 = []; self.fix8 = []
    def here(self): return self.base + len(self.buf)
    def label(self, name): self.labels[name] = self.here()
    def db(self, *bs): self.buf += bytes(bs)
    def dd(self, v): self.buf += v.to_bytes(4, 'little')
    def call(self, target): self.db(0xE8); self._rel32(target)
    def jmp32(self, target): self.db(0xE9); self._rel32(target)
    def _rel32(self, target):
        if isinstance(target, str):
            self.fix32.append((len(self.buf), target)); self.buf += b'\0\0\0\0'
        else:
            self.buf += (target - (self.here() + 4)).to_bytes(4, 'little', signed=True)
    def j8(self, opcode, label):
        self.db(opcode); self.fix8.append((len(self.buf), label)); self.db(0x00)
    def pic_delta_ecx(self):
        # ecx := runtime rebase delta (call/pop trick); clobbers ecx only
        self.call(self.here() + 5)
        popva = self.here()
        self.db(0x59)                       # pop ecx
        self.db(0x81, 0xE9); self.dd(popva)  # sub ecx, preferred-VA
    def resolve(self):
        for off, lab in self.fix32:
            self.buf[off:off+4] = (self.labels[lab] - (self.base + off + 4)).to_bytes(4, 'little', signed=True)
        for off, lab in self.fix8:
            rel = self.labels[lab] - (self.base + off + 1)
            assert -128 <= rel <= 127, "rel8 out of range for %s: %d" % (lab, rel)
            self.buf[off] = rel & 0xFF


def build_cave():
    a = Asm(CAVE_BASE)

    # ---- ring_append: ecx=delta, eax=val1(caller/tag), edx=val2(seed/extra)
    #      preserves ebx/esi/edi/ecx; clobbers nothing else callers care about
    a.label('ring_append')
    a.db(0x53)                          # push ebx
    a.db(0x56)                          # push esi
    a.db(0x8B, 0x99); a.dd(RING)        # mov ebx, [ecx+RING]      ; count
    a.db(0x8B, 0xF3)                    # mov esi, ebx
    a.db(0x83, 0xE6, RINGMASK)          # and esi, 7Fh
    a.db(0x8D, 0xB4, 0xF1); a.dd(RING + 8)  # lea esi, [ecx+esi*8+RING+8]
    a.db(0x89, 0x06)                    # mov [esi], eax
    a.db(0x89, 0x56, 0x04)              # mov [esi+4], edx
    a.db(0x43)                          # inc ebx
    a.db(0x89, 0x99); a.dd(RING)        # mov [ecx+RING], ebx
    a.db(0x5E)                          # pop esi
    a.db(0x5B)                          # pop ebx
    a.db(0xC3)                          # ret

    # ---- H1: TAoWHSMap.Random entry -----------------------------------------
    # in: eax=self(map), edx=range, [esp]=caller retaddr
    a.label('cave_random')
    a.db(0x50)                          # push eax                 ; self
    a.db(0x52)                          # push edx                 ; range
    a.db(0x51)                          # push ecx
    a.pic_delta_ecx()
    # stack: [esp]=ecx [esp+4]=range [esp+8]=self [esp+0Ch]=caller
    a.db(0x8B, 0x44, 0x24, 0x08)        # mov eax, [esp+8]         ; self
    a.db(0x8B, 0x90); a.dd(0x230)       # mov edx, [eax+0x230]     ; seed before roll
    a.db(0x8B, 0x44, 0x24, 0x0C)        # mov eax, [esp+0Ch]       ; caller
    a.call('ring_append')
    a.db(0x59)                          # pop ecx
    a.db(0x5A)                          # pop edx
    a.db(0x58)                          # pop eax
    a.db(0x53)                          # push ebx                 ; displaced
    a.db(0x56)                          # push esi
    a.db(0x8B, 0xF2)                    # mov esi, edx
    a.db(0x8B, 0xD8)                    # mov ebx, eax
    a.jmp32(H_RANDOM + 6)

    # ---- H2: TNegotiateTE.Execute entry -------------------------------------
    # in: eax=TE
    a.label('cave_negoexec')
    a.db(0x50)                          # push eax
    a.db(0x52)                          # push edx
    a.db(0x51)                          # push ecx
    a.pic_delta_ecx()
    a.db(0xFF, 0x81); a.dd(SCRATCH)     # inc dword [ecx+SCRATCH]  ; exec count
    a.db(0x8A, 0x50, 0x1C)              # mov dl, [eax+1Ch]        ; player
    a.db(0x88, 0x91); a.dd(SCRATCH + 4)
    a.db(0x8A, 0x50, 0x15)              # mov dl, [eax+15h]        ; x
    a.db(0x88, 0x91); a.dd(SCRATCH + 5)
    a.db(0x8A, 0x50, 0x16)              # mov dl, [eax+16h]        ; y
    a.db(0x88, 0x91); a.dd(SCRATCH + 6)
    a.db(0x8A, 0x50, 0x17)              # mov dl, [eax+17h]        ; lvl
    a.db(0x88, 0x91); a.dd(SCRATCH + 7)
    a.db(0x8B, 0x50, 0x10)              # mov edx, [eax+10h]       ; paid
    a.db(0x89, 0x91); a.dd(SCRATCH + 8)
    a.db(0x8A, 0x50, 0x2E)              # mov dl, [eax+2Eh]        ; accept
    a.db(0x88, 0x91); a.dd(SCRATCH + 0x0C)
    a.db(0x8A, 0x50, 0x2D)              # mov dl, [eax+2Dh]        ; flags
    a.db(0x88, 0x91); a.dd(SCRATCH + 0x0D)
    a.db(0x8A, 0x50, 0x24)              # mov dl, [eax+24h]        ; mode
    a.db(0x88, 0x91); a.dd(SCRATCH + 0x0E)
    a.db(0x8B, 0x50, 0x10)              # mov edx, [eax+10h]       ; extra = paid
    a.db(0xB8); a.dd(TAG_NEGO)          # mov eax, 'NEGO'
    a.call('ring_append')
    a.db(0x59)                          # pop ecx
    a.db(0x5A)                          # pop edx
    a.db(0x58)                          # pop eax
    a.db(0x53)                          # push ebx                 ; displaced
    a.db(0x83, 0xC4, 0xE0)              # add esp, -20h
    a.db(0x8B, 0xD8)                    # mov ebx, eax
    a.jmp32(H_NEGOEX + 6)

    # ---- H3: IncommingNegotiateOffer entry ----------------------------------
    # in: eax=army, edx=TE
    a.label('cave_offer')
    a.db(0x50)                          # push eax
    a.db(0x52)                          # push edx
    a.db(0x51)                          # push ecx
    a.pic_delta_ecx()
    a.db(0xFF, 0x81); a.dd(SCRATCH + 0x10)  # inc dword offer count
    a.db(0x8B, 0x42, 0x10)              # mov eax, [edx+10h]       ; paid
    a.db(0x89, 0x81); a.dd(SCRATCH + 0x14)
    a.db(0x8A, 0x42, 0x24)              # mov al, [edx+24h]        ; mode
    a.db(0x88, 0x81); a.dd(SCRATCH + 0x18)
    a.db(0x8A, 0x42, 0x2E)              # mov al, [edx+2Eh]        ; accept
    a.db(0x88, 0x81); a.dd(SCRATCH + 0x19)
    a.db(0x8A, 0x42, 0x2D)              # mov al, [edx+2Dh]        ; flags
    a.db(0x88, 0x81); a.dd(SCRATCH + 0x1A)
    a.db(0x8A, 0x42, 0x1C)              # mov al, [edx+1Ch]        ; player
    a.db(0x88, 0x81); a.dd(SCRATCH + 0x1B)
    a.db(0x8B, 0x52, 0x10)              # mov edx, [edx+10h]       ; extra = paid
    a.db(0xB8); a.dd(TAG_OFFR)          # mov eax, 'OFFR'
    a.call('ring_append')
    a.db(0x59)                          # pop ecx
    a.db(0x5A)                          # pop edx
    a.db(0x58)                          # pop eax
    a.db(0x55)                          # push ebp                 ; displaced
    a.db(0x8B, 0xEC)                    # mov ebp, esp
    a.db(0x83, 0xC4, 0xC0)              # add esp, -40h
    a.jmp32(H_OFFER + 6)

    # ---- H4: after GetJoinSelection (al = selection bitmask) ----------------
    a.label('cave_sel')
    a.db(0x50)                          # push eax
    a.db(0x52)                          # push edx
    a.db(0x51)                          # push ecx
    a.pic_delta_ecx()
    a.db(0x88, 0x81); a.dd(SCRATCH + 0x1C)  # mov [ecx+..], al     ; selection
    a.db(0x0F, 0xB6, 0xD0)              # movzx edx, al
    a.db(0xB8); a.dd(TAG_SELE)          # mov eax, 'SELE'
    a.call('ring_append')
    a.db(0x59)                          # pop ecx
    a.db(0x5A)                          # pop edx
    a.db(0x58)                          # pop eax
    a.db(0x88, 0x45, 0xFB)              # mov [ebp-5], al          ; displaced
    a.db(0x8A, 0x55, 0xFB)              # mov dl, [ebp-5]
    a.jmp32(H_SEL + 6)

    # ---- H5: JoinAmount compare (eax = amount, ebx = TE) --------------------
    a.label('cave_amt')
    a.db(0x50)                          # push eax
    a.db(0x52)                          # push edx
    a.db(0x51)                          # push ecx
    a.pic_delta_ecx()
    a.db(0x89, 0x81); a.dd(SCRATCH + 0x20)  # mov [ecx+..], eax    ; amount
    a.db(0x8B, 0xD0)                    # mov edx, eax
    a.db(0xB8); a.dd(TAG_AMNT)          # mov eax, 'AMNT'
    a.call('ring_append')
    a.db(0x59)                          # pop ecx
    a.db(0x5A)                          # pop edx
    a.db(0x58)                          # pop eax
    a.db(0x3B, 0x43, 0x10)              # cmp eax, [ebx+10h]       ; replicated
    a.j8(0x7F, 'amt_bail')              # jg  amt_bail
    a.jmp32(AMT_FALL)                   # not greater -> join proceeds
    a.label('amt_bail')
    a.db(0x51)                          # push ecx
    a.pic_delta_ecx()
    a.db(0xFF, 0x81); a.dd(SCRATCH + 0x28)  # inc dword bail count
    a.db(0x59)                          # pop ecx
    a.jmp32(AMT_BAIL)                   # original jg target (silently no join)

    # ---- H6: join-done (BeginUpdate branch reached) -------------------------
    a.label('cave_join')
    a.db(0x50)                          # push eax (dead, but cheap)
    a.db(0x52)                          # push edx
    a.db(0x51)                          # push ecx
    a.pic_delta_ecx()
    a.db(0xFF, 0x81); a.dd(SCRATCH + 0x24)  # inc dword join-done count
    a.db(0x33, 0xD2)                    # xor edx, edx
    a.db(0xB8); a.dd(TAG_JOIN)          # mov eax, 'JOIN'
    a.call('ring_append')
    a.db(0x59)                          # pop ecx
    a.db(0x5A)                          # pop edx
    a.db(0x58)                          # pop eax
    a.db(0x8B, 0xC6)                    # mov eax, esi             ; displaced
    a.call(BEGINUPD)                    # call BeginUpdate
    a.jmp32(JOIN_BACK)

    a.resolve()
    assert CAVE_BASE + len(a.buf) <= CAVE_LIMIT, "cave overflow: %d" % len(a.buf)
    return bytes(a.buf) + bytes(CAVE_LIMIT - CAVE_BASE - len(a.buf)), a.labels


def jmp_patch(site, target, oldlen):
    rel = target - (site + 5)
    return bytes([0xE9]) + rel.to_bytes(4, 'little', signed=True) + b'\x90' * (oldlen - 5)


def main():
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    data = bytearray(open(TARGET, "rb").read())
    dirty = False
    ok = True

    cave, labels = build_cave()
    print("cave: %d bytes used @0x%X (file 0x%X)" %
          (len(cave.rstrip(b'\0')), CAVE_BASE, CAVE_BASE - VA2FILE))

    sites = (
        ("H1 Random entry",        H_RANDOM, 'cave_random'),
        ("H2 NegotiateTE.Execute", H_NEGOEX, 'cave_negoexec'),
        ("H3 Offer entry",         H_OFFER,  'cave_offer'),
        ("H4 GetJoinSelection",    H_SEL,    'cave_sel'),
        ("H5 JoinAmount cmp",      H_AMT,    'cave_amt'),
        ("H6 join-done",           H_JOIN,   'cave_join'),
    )

    # cave range
    off = CAVE_BASE - VA2FILE
    cur = bytes(data[off:off+len(cave)])
    cave_new = bytes(CAVE_LIMIT - CAVE_BASE) if revert else cave
    if cur == cave_new:
        print("  %-26s already %s" % ("cave", "clear" if revert else "applied"))
    elif cur == bytes(len(cave)) or cur[:2] in (cave[:2],):
        data[off:off+len(cave_new)] = cave_new
        print("  %-26s %s" % ("cave", "clearing" if revert else "ready"))
        dirty = True
    else:
        print("  %-26s MISMATCH: %s..." % ("cave", cur[:16].hex()))
        ok = False

    for name, va, lab in sites:
        old = OLD[va]
        new = old if revert else jmp_patch(va, labels[lab], len(old))
        off = va - VA2FILE
        cur = bytes(data[off:off+len(old)])
        if cur == new:
            print("  %-26s already applied" % name)
        elif cur == old or (cur[0] == 0xE9 and not revert) or (revert and cur[0] == 0xE9):
            data[off:off+len(new)] = new
            print("  %-26s ready @0x%X (%d bytes)" % (name, va, len(new)))
            dirty = True
        else:
            print("  %-26s MISMATCH @0x%X: %s..." % (name, va, cur[:16].hex()))
            ok = False

    if not ok:
        print("ABORT: unexpected bytes, nothing written.")
        return 1
    if not dirty:
        print("Nothing to do.")
        return 0
    if not apply and not revert:
        print("Dry run OK - rerun with --apply to write (--revert to remove).")
        return 0

    if not os.path.exists(BACKUP):
        shutil.copy2(TARGET, BACKUP)
        print("Backup -> %s" % os.path.basename(BACKUP))
    with open(TARGET, "wb") as f:
        f.write(data)
    print("Written %s" % TARGET)
    return 0


if __name__ == "__main__":
    sys.exit(main())

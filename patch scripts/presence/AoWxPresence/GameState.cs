// Game state for the presence line, read from AoWEPACK.dll (see memory presence-game-state-re / presence_probe.py):
//   map    = [AoWEPACK+0x1FA040]           AoWE.AoWHSMap global, nil when no map is loaded
//   conn   = byte  [map+0x13A]              TPlayerConnectionType 0 local / 1 network / 2 email
//   humans = [[[map+0x140]+0x1C]+8]         local human count (>1 = hotseat)
//   name   = AnsiString [map+0xE4]          map title (hsm tag 0x19)
//   turn   = int32 [map+0x174]
//   seat   = int8  [map+0xA5]               local (seated) player index, -1 briefly during a hotseat new day
//   player = [[[map+0x140]+8]+4][seat*4] (TPlayerList +8 = TList: items +4, count +8), race = byte [player+0xA5]
using System;

namespace AoWxPresence
{
    internal sealed class GameInfo
    {
        internal bool Multiplayer;
        internal string Map, Race;
        internal int Turn;
    }

    internal sealed class GameState : IDisposable
    {
        static readonly string[] Races = { "Humans", "Azracs", "Lizardmen", "Frostlings", "Elves", "Halflings",
                                           "Dwarves", "High Men", "Dark Elves", "Orcs", "Goblins", "Undead" };
        const uint MapGlobalRva = 0x1FA040;

        readonly Memory mem;
        uint epack;
        string lastRace;

        internal GameState(int pid) { mem = new Memory(pid); }

        // null = not in a game (title screen, menus, lobby) or unreadable
        internal GameInfo Read()
        {
            if (!mem.Ok) return null;
            try
            {
                if (epack == 0) epack = mem.ModuleBase("AoWEPACK.dll");
                if (epack == 0) return null;
                uint map = mem.U32(epack + MapGlobalRva);
                if (map == 0) { lastRace = null; return null; }
                int turn = mem.I32(map + 0x174);
                if (turn < 1 || turn > 100000) return null;
                GameInfo g = new GameInfo();
                g.Turn = turn;
                g.Map = mem.AnsiStr(mem.U32(map + 0xE4)).Trim();
                uint ctl = mem.U32(map + 0x140);
                int humans = 0;
                if (ctl != 0)
                {
                    uint locals = mem.U32(ctl + 0x1C);
                    if (locals != 0) humans = mem.I32(locals + 8);
                }
                byte conn = mem.U8(map + 0x13A);
                g.Multiplayer = conn == 1 || conn == 2 || humans > 1;
                sbyte seat = (sbyte)mem.U8(map + 0xA5);
                if (seat >= 0 && ctl != 0)
                {
                    uint tlist = mem.U32(ctl + 8);                     // TPlayerList's TList of TPlayer
                    uint items = tlist == 0 ? 0 : mem.U32(tlist + 4);
                    int count = tlist == 0 ? 0 : mem.I32(tlist + 8);
                    if (items != 0 && seat < count)
                    {
                        uint player = mem.U32(items + (uint)seat * 4);
                        byte race = player == 0 ? (byte)255 : mem.U8(player + 0xA5);
                        lastRace = race < Races.Length ? Races[race] : null;
                    }
                }
                g.Race = lastRace;
                return g;
            }
            catch (InvalidOperationException) { epack = 0; return null; }
        }

        public void Dispose() { mem.Dispose(); }
    }
}

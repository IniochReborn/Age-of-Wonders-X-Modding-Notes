r"""
Register the /map slash command for the AoWx map randomizer app (run once; rerun only if the command changes).

  py -3.10 register_command.py <APPLICATION_ID> <BOT_TOKEN>              global command
  py -3.10 register_command.py <APPLICATION_ID> <BOT_TOKEN> <SERVER_ID>  only that server (shows up instantly)

The token is only sent to discord.com and is not stored anywhere.
"""
import json, sys, urllib.request

CMD = [{"name": "map", "type": 1, "description": "Roll a random AoWx map and a race for each player"}]


def main():
    if len(sys.argv) not in (3, 4):
        print(__doc__); return 1
    app, token = sys.argv[1], sys.argv[2]
    url = "https://discord.com/api/v10/applications/%s/%scommands" % (app, "guilds/%s/" % sys.argv[3] if len(sys.argv) == 4 else "")
    req = urllib.request.Request(url, data=json.dumps(CMD).encode(), method="PUT", headers={
        "Authorization": "Bot " + token, "Content-Type": "application/json",
        "User-Agent": "DiscordBot (https://aowx.org, 1.0)"})
    try:
        with urllib.request.urlopen(req) as r:
            print("registered:", ", ".join("/" + c["name"] for c in json.load(r)))
    except urllib.error.HTTPError as e:
        print("Discord said %d: %s" % (e.code, e.read().decode(errors="replace"))); return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/bin/sh
# occam hook. `occam.sh session` prints the ruleset (SessionStart context);
# `occam.sh subagent` prints the SubagentStart JSON. Level: $OCCAM_LEVEL = full (default) | lite | off.
root=${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}
lvl=${OCCAM_LEVEL:-full}
case $lvl in off) exit 0 ;; lite) ;; *) lvl=full ;; esac
[ "$1" = subagent ] && exec cat "$root/hooks/subagent.json"
if [ "$lvl" = lite ]; then
  echo 'OCCAM MODE (lite): build as usual, but work lean and talk less. Switch: /occam:occam full|off.'
  awk '/^## /{skip = /^## Build less/} !skip' "$root/skills/occam/rules.md"
else
  echo 'OCCAM MODE (full). Switch: /occam:occam lite|off.'
  cat "$root/skills/occam/rules.md"
fi

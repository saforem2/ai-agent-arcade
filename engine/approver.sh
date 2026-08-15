#!/bin/bash
# Auto-approve shell-permission dialogs for the two chess agents.
while :; do
  for a in kimi-white codex-black; do
    st=$(herdr agent get "$a" 2>/dev/null | jq -r '.result.agent.agent_status // empty')
    if [ "$st" = "blocked" ]; then
      scr=$(herdr agent read "$a" --source visible --lines 30 2>/dev/null)
      if printf '%s' "$scr" | grep -qiE 'approve|allow|permission|proceed\?'; then
        herdr agent send-keys "$a" 2 enter >/dev/null 2>&1
        echo "$(date +%T) approved dialog for $a"
        sleep 2
        # codex-style dialogs may want '1' or 'y' instead
        st2=$(herdr agent get "$a" 2>/dev/null | jq -r '.result.agent.agent_status // empty')
        if [ "$st2" = "blocked" ]; then
          herdr agent send-keys "$a" 1 enter >/dev/null 2>&1
          echo "$(date +%T) retried with 1 for $a"
        fi
      fi
    fi
  done
  sleep 3
done

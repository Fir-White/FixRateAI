#!/usr/bin/env bash
# Both providers execute this file from trusted GitHub main, never an event ref.
set -euo pipefail
for required in GITVERSE_USERNAME GITVERSE_TOKEN GH_MIRROR_SSH_KEY; do
  test -n "${!required:-}" || { echo "::error::Missing $required secret"; exit 1; }
done
export GIT_TERMINAL_PROMPT=0
umask 077
credentials="$(mktemp -d "${RUNNER_TEMP:-/tmp}/git-sync-auth.XXXXXX")"
trap 'rm -rf -- "$credentials"' EXIT
printf '%s\n' "$GH_MIRROR_SSH_KEY" > "$credentials/key"
unset GH_MIRROR_SSH_KEY
curl --fail --silent --show-error --retry 3 --retry-all-errors --connect-timeout 15 --max-time 60 \
  https://api.github.com/meta > "$credentials/meta.json"
python3 - "$credentials" <<'PY'
import json, pathlib, sys
directory = pathlib.Path(sys.argv[1])
keys = json.loads((directory / 'meta.json').read_text())['ssh_keys']
if not keys or not all(isinstance(key, str) and key.startswith(('ssh-', 'ecdsa-')) and '\n' not in key for key in keys):
    raise ValueError('Invalid GitHub SSH host metadata')
(directory / 'known_hosts').write_text(''.join('github.com ' + key + '\n' for key in keys))
PY
export GIT_SSH_COMMAND="ssh -i \"$credentials/key\" -o IdentitiesOnly=yes -o BatchMode=yes -o UserKnownHostsFile=\"$credentials/known_hosts\" -o StrictHostKeyChecking=yes -o ConnectTimeout=20"
export GIT_ASKPASS="$credentials/askpass.sh"
cat > "$GIT_ASKPASS" <<'ASKPASS'
#!/usr/bin/env bash
case "$1" in
  *sername*) printf '%s\n' "$GITVERSE_USERNAME" ;;
  *assword*) printf '%s\n' "$GITVERSE_TOKEN" ;;
  *) exit 1 ;;
esac
ASKPASS
chmod 700 "$GIT_ASKPASS"
export GIT_CONFIG_COUNT=1
export GIT_CONFIG_KEY_0=credential.helper
export GIT_CONFIG_VALUE_0=''
report="${SYNC_REPORT_PATH:-${RUNNER_TEMP:-/tmp}/git-sync-report.json}"
script_directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
result=0
python3 "$script_directory/sync_git_hosts.py" \
  --github 'git@github.com:Fir-White/FixRateAI.git' \
  --gitverse 'https://gitverse.ru/firewhite/FixRate_AI' \
  --attempts 3 --report "$report" || result=$?
summary="${GITHUB_STEP_SUMMARY:-${GITVERSE_STEP_SUMMARY:-}}"
if test -f "$report" && test -n "$summary"; then
  printf '### GitHub / GitVerse synchronization\n\n```json\n' >> "$summary"
  cat "$report" >> "$summary"
  printf '\n```\n' >> "$summary"
fi
if test "$result" -ne 0; then
  echo '::error::Synchronization did not converge. Inspect conflicting refs or failed operation in the report.'
fi
exit "$result"

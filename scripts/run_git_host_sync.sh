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
# Reviewed pins from https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints
# Keep these in the shared entrypoint so existing sparse checkouts can run it
# without a new file or an anonymous REST request from either provider.
cat > "$credentials/known_hosts" <<'KNOWN_HOSTS'
github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl
github.com ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBEmKSENjQEezOmxkZMy7opKgwFB9nkt5YRrYMjNuG5N87uRgg6CLrbo5wAdT/y6v0mKV0U2w0WZ2YB/++Tpockg=
github.com ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCj7ndNxQowgcQnjshcLrqPEiiphnt+VTTvDP6mHBL9j1aNUkY4Ue1gvwnGLVlOhGeYrnZaMgRK6+PKCUXaDbC7qtbW8gIkhL7aGCsOr/C56SJMy/BCZfxd1nWzAOxSDPgVsmerOBYfNqltV9/hWCqBywINIR+5dIg6JTJ72pcEpEjcYgXkE2YEFXV1JHnsKgbLWNlhScqb2UmyRkQyytRLtL+38TGxkxCflmO+5Z8CSSNY7GidjMIZ7Q4zMjA2n1nGrlTDkzwDCsw+wqFPGQA179cnfGWOWRVruj16z6XyvxvjJwbz0wQZ75XK5tKSb7FNyeIEs4TT4jk+S4dhPeAUC5y+bDYirYgM4GC7uEnztnZyaVWQ7B381AK4Qdrwt51ZqExKbQpTUNn+EjqoTwvqNj4kqx5QUCI0ThS/YkOxJCXmPUWZbhjpCg56i+2aB6CmK2JGhn57K5mj0MNdBXA4/WnwH6XoPWJzK5Nyu2zB3nAZp+S5hpQs+p1vN1/wsjk=
KNOWN_HOSTS
export GIT_SSH_COMMAND="ssh -F /dev/null -i \"$credentials/key\" \
  -o IdentitiesOnly=yes -o BatchMode=yes -o UserKnownHostsFile=\"$credentials/known_hosts\" \
  -o GlobalKnownHostsFile=/dev/null -o StrictHostKeyChecking=yes -o UpdateHostKeys=no -o ConnectTimeout=20"
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

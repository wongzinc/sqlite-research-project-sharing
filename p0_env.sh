#!/bin/sh
# p0_env.sh — pin + record the environment knobs that drive cold-start latency.
#
# Run ONCE at the start of a P0 master batch (needs root for the sysfs writes).
# Prints a single "P0_ENV ..." line on stdout that the runner embeds into every
# run record, so any later environment drift is visible after the fact.
#
# Locked knobs (IMPLEMENTATION_PIPELINES.md §3.0 F4/F5/F6):
#   CPU governor    -> performance      (cold-start us is frequency-sensitive)
#   read_ahead_kb   -> $RA_KB (def 128) (caps madvise load = 2*ra_pages; F5)
#   THP             -> madvise
#
# Usage:  p0_env.sh [db_path_or_dir]      (default: current dir)
#         RA_KB=<n> p0_env.sh ...         (override read_ahead_kb; default 128)
#
# Writes are best-effort: if not root, it warns but still prints the read-back
# values so a recording-only (non-pinning) invocation still works.
set -u

TARGET="${1:-.}"
RA_KB="${RA_KB:-128}"

warn() { echo "p0_env: WARN $*" >&2; }

# --- resolve the whole-disk block device backing TARGET ---
SRC=$(df --output=source "$TARGET" 2>/dev/null | tail -1)
PART=$(basename "${SRC:-unknown}")
if [ -e "/sys/block/$PART/queue/read_ahead_kb" ]; then
  DISK="$PART"                                                  # PART is itself a whole disk (e.g. nvme0n1 mounted directly): no suffix to strip
else
  DISK=$(lsblk -no pkname "/dev/$PART" 2>/dev/null | head -1)   # partition -> parent disk
  [ -z "${DISK:-}" ] && DISK=$(printf '%s' "$PART" | sed -E 's/p?[0-9]+$//')   # fallback: strip partition suffix (sdaN / nvme..pN)
fi
RA_PATH="/sys/block/$DISK/queue/read_ahead_kb"

# --- pin (best-effort) ---
for g in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
  [ -e "$g" ] || continue
  if [ -w "$g" ]; then echo performance > "$g" 2>/dev/null || warn "set governor failed ($g)";
  else warn "no write perm: $g (need root)"; fi
done
if [ -w "$RA_PATH" ]; then echo "$RA_KB" > "$RA_PATH" 2>/dev/null || warn "set read_ahead_kb failed";
else warn "no write perm: $RA_PATH (need root)"; fi
THP=/sys/kernel/mm/transparent_hugepage/enabled
if [ -w "$THP" ]; then echo madvise > "$THP" 2>/dev/null || warn "set THP failed";
else warn "no write perm: $THP (need root)"; fi

# --- record (read back actual effective values) ---
CPU0=/sys/devices/system/cpu/cpu0/cpufreq
gov=$(cat "$CPU0/scaling_governor" 2>/dev/null || echo NA)
ra=$(cat "$RA_PATH" 2>/dev/null || echo NA)
thp=$(sed -E 's/.*\[([a-z]+)\].*/\1/' "$THP" 2>/dev/null || echo NA)
load=$(cut -d' ' -f1 /proc/loadavg 2>/dev/null || echo NA)
memfree=$(awk '/MemAvailable/{print $2}' /proc/meminfo 2>/dev/null || echo NA)
# Frequency policy: under amd-pstate-epp the "governor" label (often powersave) does NOT pin
# low freq -- the EPP knob does. Record driver/epp/boost/maxfreq so the artifact proves the
# real policy (e.g. epp=performance boost=1 => cores race to max under load) regardless of label.
driver=$(cat "$CPU0/scaling_driver" 2>/dev/null || echo NA)
epp=$(cat "$CPU0/energy_performance_preference" 2>/dev/null || echo NA)
boost=$(cat /sys/devices/system/cpu/cpufreq/boost 2>/dev/null || echo NA)
maxfreq=$(cat "$CPU0/cpuinfo_max_freq" 2>/dev/null || echo NA)

printf 'P0_ENV kernel=%s disk=%s ra_kb=%s governor=%s driver=%s epp=%s boost=%s maxfreq_khz=%s thp=%s loadavg=%s memavail_kb=%s\n' \
  "$(uname -r)" "$DISK" "$ra" "$gov" "$driver" "$epp" "$boost" "$maxfreq" "$thp" "$load" "$memfree"

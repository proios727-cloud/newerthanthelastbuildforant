#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
touch runtime/HALT
printf "%s\n" "Paper HALT requested; inspect process shutdown."

#!/bin/sh
# Keep the planning CLI separate from the Python integration's dependencies.
set -eu
exec npm exec --yes --package=@fission-ai/openspec@1.16.0 -- openspec "$@"

#!/bin/bash
# Run a command with the optional corporate CA applied (#337): for entry points that do not
# go through entrypoint.sh, e.g. the daemon: `with-extra-ca.sh python manage.py run_daemon`.
. "$(dirname "$0")/extra-ca.sh" || exit 1
exec "$@"

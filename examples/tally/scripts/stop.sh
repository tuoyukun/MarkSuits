#!/usr/bin/env bash
# Shipped by Mark. Stops what start.sh started, from each module's stop.sh.
exec bash "$(dirname "$0")/each.sh" stop.sh optional "app"

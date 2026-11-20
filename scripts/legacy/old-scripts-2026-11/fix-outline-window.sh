#!/bin/bash
sleep 15
WINDOW_ID=$(xdotool search --class "Outline" 2>/dev/null | head -1)
if [ -n "$WINDOW_ID" ]; then
    wmctrl -i -r "$WINDOW_ID" -b remove,above
fi

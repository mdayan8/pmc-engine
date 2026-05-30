#!/bin/bash
# PMC Engine — UserPromptSubmit Hook
# Intercepts user prompt, runs PMC compression, prepends context.
# Install: Add to .claude/settings.json as UserPromptSubmit hook.
#
# Input (stdin): JSON with UserPromptSubmit event data
# Output (stdout): Modified prompt JSON with compressed context

set -euo pipefail

# Read the event from stdin
EVENT=$(cat)

# Extract the user prompt
PROMPT=$(echo "$EVENT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data.get('params', {}).get('content', ''))
" 2>/dev/null || echo "")

if [ -z "$PROMPT" ]; then
    echo "$EVENT"
    exit 0
fi

# Run PMC compression (silent)
COMPRESSED=$(pmc compress "$PROMPT" --json 2>/dev/null || echo "")

if [ -n "$COMPRESSED" ] && [ "$COMPRESSED" != "null" ]; then
    # Extract context string from JSON result
    CONTEXT=$(echo "$COMPRESSED" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data.get('context_string', ''))
" 2>/dev/null || echo "")

    if [ -n "$CONTEXT" ]; then
        # Prepend compressed context to the prompt
        MODIFIED="${CONTEXT}\n\n${PROMPT}"
        echo "$EVENT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
if 'params' in data:
    data['params']['content'] = '''${CONTEXT}

${PROMPT}'''
print(json.dumps(data))
" 2>/dev/null || echo "$EVENT"
        exit 0
    fi
fi

# Pass through unmodified if compression failed
echo "$EVENT"
exit 0

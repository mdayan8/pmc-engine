#!/bin/bash
# PMC Engine — PreToolUse Hook
# Intercepts Read tool calls and returns AST-compressed file content.
# Install: Add to .claude/settings.json as PreToolUse hook.
#
# Input (stdin): JSON with PreToolUse event data
# Output (stdout): Modified response with compressed content

set -euo pipefail

EVENT=$(cat)

# Extract tool name and arguments
TOOL_NAME=$(echo "$EVENT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
params = data.get('params', {})
tool = params.get('tool', params.get('name', ''))
print(tool)
" 2>/dev/null || echo "")

# Only intercept Read tool calls
if [ "$TOOL_NAME" != "Read" ] && [ "$TOOL_NAME" != "read_file" ] && [ "$TOOL_NAME" != "read" ]; then
    echo "$EVENT"
    exit 0
fi

# Extract file path
FILEPATH=$(echo "$EVENT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
params = data.get('params', {})
args = params.get('args', params.get('arguments', {}))
print(args.get('file_path', args.get('path', '')))
" 2>/dev/null || echo "")

if [ -z "$FILEPATH" ] || [ ! -f "$FILEPATH" ]; then
    echo "$EVENT"
    exit 0
fi

# Skip binary files
if file "$FILEPATH" | grep -q "binary"; then
    echo "$EVENT"
    exit 0
fi

# Only compress code files
EXT="${FILEPATH##*.}"
case "$EXT" in
    py|js|ts|tsx|jsx|go|rs|java|rb|php|c|cpp|h|hpp|swift|kt|scala)
        # Compress the file via MCP resource endpoint
        COMPRESSED=$(pmc compress "read file $(basename $FILEPATH)" --source "$(dirname $FILEPATH)/.." --json 2>/dev/null || echo "")
        if [ -n "$COMPRESSED" ]; then
            echo "$EVENT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(json.dumps({
    'type': 'response',
    'content': '# File compressed by PMC Engine\n# Run [EXPAND: symbol_name] for full source\n'
}))
" 2>/dev/null || echo "$EVENT"
            exit 0
        fi
        ;;
esac

echo "$EVENT"
exit 0

#!/bin/sh
# Install the git post-commit hook
HOOK_DIR="$(git rev-parse --git-dir)/hooks"
mkdir -p "$HOOK_DIR"
cp hooks/post-commit "$HOOK_DIR/post-commit"
chmod +x "$HOOK_DIR/post-commit"
echo "post-commit hook installed to $HOOK_DIR/post-commit"

#!/usr/bin/env bash
# Generate git-sha.tex before Quarto renders report.qmd
SHA=$(git -C "$(git rev-parse --show-toplevel)" rev-parse HEAD 2>/dev/null || echo "unknown")
echo "\\def\\gitsha{${SHA}}" > git-sha.tex

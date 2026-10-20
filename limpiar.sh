#!/bin/bash
WM="http://127.0.0.1:8765"

find . -type f \( -name "*.sol" -o -name "*.js" -o -name "*.ts" -o -name "*.py" -o -name "*.go" -o -name "*.java" -o -name "*.cs" \) -not -path "*/.git/*" -not -path "*/node_modules/*" -not -path "*/.venv/*" -not -path "*/venv/*" -not -path "*/__pycache__/*" -not -path "*/build/*" -not -path "*/dist/*" -not -path "*/artifacts/*" -not -path "*/cache/*" -not -name "*.cleaned.*" | while read -r f; do
  payload="{\"file\": \"$(base64 -w0 "$f")\", \"name\": \"$(basename "$f")\"}"
  r=$(curl -s -X POST "$WM/inspect" -H 'Content-Type: application/json' -d "$payload")
  echo "$f  ->  invisibles: $(echo "$r" | jq -r '.report.suspicious_total')  |  sospechoso: $(echo "$r" | jq -r '.suspicious.verdict')"
done

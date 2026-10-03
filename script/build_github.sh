#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ $# -ne 0 ]]; then
    echo "Uso: $0"
    echo "Compila a variante GitHub em build/Release/Isis DICOM Viewer.app."
    echo "Inclui plugins e atualizador; sem sandbox no aplicativo principal."
    echo "Assinatura local ad hoc. Developer ID e notarização são etapas de distribuição."
    [[ $# -eq 1 && "$1" == --help ]] && exit 0
    exit 2
fi
export ISIS_BUILD_CHANNEL=github
exec "$ROOT_DIR/script/build_release.sh"

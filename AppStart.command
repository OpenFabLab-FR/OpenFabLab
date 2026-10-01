#!/bin/zsh

# Lanceur macOS : un double-clic ouvre OpenFabLab dans Safari.
PROJECT_DIR=${0:A:h}
APPLICATION_URL="http://localhost:5001"
APPLICATION_PORT="5001"

cd "$PROJECT_DIR" || exit 1

show_error_and_wait() {
    echo
    echo "Le démarrage a échoué. Lisez le message ci-dessus."
    echo "Appuyez sur une touche pour fermer cette fenêtre."
    read -k 1
    exit 1
}

if [[ ! -x ".venv/bin/python" ]]; then
    echo "Première préparation d'OpenFabLab…"
    python3 -m venv .venv || show_error_and_wait
fi

if ! .venv/bin/python -c "import flask, segno, PIL, resvg_py" >/dev/null 2>&1; then
    echo "Installation des composants d'OpenFabLab…"
    .venv/bin/python -m pip install -r requirements.txt || show_error_and_wait
fi

# Une ancienne instance lancée depuis ce même dossier peut continuer à servir
# l'ancien code. On l'arrête proprement avant d'ouvrir la nouvelle version.
if command -v lsof >/dev/null 2>&1; then
    EXISTING_PID=$(lsof -tiTCP:"$APPLICATION_PORT" -sTCP:LISTEN 2>/dev/null | head -n 1)
    if [[ -n "$EXISTING_PID" ]]; then
        EXISTING_CWD=$(lsof -a -p "$EXISTING_PID" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1)
        if [[ "$EXISTING_CWD" == "$PROJECT_DIR" ]]; then
            echo "Arrêt de l'ancienne instance d'OpenFabLab…"
            kill "$EXISTING_PID" 2>/dev/null || show_error_and_wait
            for attempt in {1..30}; do
                if ! kill -0 "$EXISTING_PID" 2>/dev/null; then
                    break
                fi
                sleep 0.1
            done
            if kill -0 "$EXISTING_PID" 2>/dev/null; then
                echo "L'ancienne instance n'a pas pu être arrêtée proprement."
                show_error_and_wait
            fi
        else
            echo "Le port $APPLICATION_PORT est déjà utilisé par une autre application."
            echo "Fermez cette application ou libérez le port avant de relancer OpenFabLab."
            show_error_and_wait
        fi
    fi
fi

echo "OpenFabLab démarre sur $APPLICATION_URL"
echo "Gardez cette fenêtre ouverte. Pour arrêter : Ctrl + C."
echo

(
    for attempt in {1..50}; do
        if curl -fsS "$APPLICATION_URL/sante" >/dev/null 2>&1; then
            open "$APPLICATION_URL"
            exit 0
        fi
        sleep 0.1
    done
) &
exec .venv/bin/python app.py

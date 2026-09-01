#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
WORKSPACE="${ROOT}/.runtime/local-deployment"
COMPOSE_FILE="${WORKSPACE}/compose.yaml"
GENERATOR="${ROOT}/deployment/local/generate_compose.py"
BUNDLER="${ROOT}/deployment/processes/bundle.py"
PYTHON_VERSION="3.14.2"

fail() {
    printf '%s\n' "$1" >&2
    exit 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"
}

compose() {
    docker compose -f "${COMPOSE_FILE}" "$@"
}

require_compose_file() {
    [[ -f "${COMPOSE_FILE}" ]] || fail "Local Compose workspace not found. Run: scripts/local-process.sh up"
}

validate_uv() {
    require_command uv
}

validate_docker() {
    require_command docker
    docker compose version >/dev/null 2>&1 || fail "Docker Compose is not available"
}

validate_artifacts() {
    uv run --python "${PYTHON_VERSION}" --no-python-downloads --no-project \
        "${GENERATOR}" validate \
        --repository-root "${ROOT}"
}

validate_workspace_contract() {
    require_compose_file
    uv run --python "${PYTHON_VERSION}" --no-python-downloads --no-project \
        "${GENERATOR}" validate-workspace \
        --repository-root "${ROOT}" \
        --workspace-root "${WORKSPACE}"
}

generate_workspace() {
    local volume_mode="$1"
    uv run --python "${PYTHON_VERSION}" --no-python-downloads --no-project \
        "${GENERATOR}" generate \
        --repository-root "${ROOT}" \
        --workspace-root "${WORKSPACE}" \
        --volume-mode "${volume_mode}"
}

command_prepare() {
    validate_uv
    if [[ "${1:-}" == "--scope" ]]; then
        [[ "$#" -ge 3 ]] || fail "Usage: scripts/local-process.sh prepare --scope SCOPE --all|PROCESS [PROCESS ...]"
        local scope="$2"
        shift 2
        if [[ "${1:-}" == "--all" ]]; then
            [[ "$#" -eq 1 ]] || fail "Usage: scripts/local-process.sh prepare --scope SCOPE --all"
            uv run --python "${PYTHON_VERSION}" --no-python-downloads --no-project \
                "${BUNDLER}" \
                --scope "${scope}" \
                --repository-root "${ROOT}" \
                --output-root "${ROOT}/artifacts/processes"
        else
            uv run --python "${PYTHON_VERSION}" --no-python-downloads --no-project \
                "${BUNDLER}" \
                --scope "${scope}" \
                --repository-root "${ROOT}" \
                --output-root "${ROOT}/artifacts/processes" \
                "$@"
        fi
    elif [[ "${1:-}" == "--all" ]]; then
        [[ "$#" -eq 1 ]] || fail "Usage: scripts/local-process.sh prepare --all"
        uv run --python "${PYTHON_VERSION}" --no-python-downloads --no-project \
            "${BUNDLER}" \
            --repository-root "${ROOT}" \
            --output-root "${ROOT}/artifacts/processes"
    else
        [[ "$#" -ge 1 ]] || fail "Usage: scripts/local-process.sh prepare [--scope SCOPE] --all|PROCESS [PROCESS ...]"
        uv run --python "${PYTHON_VERSION}" --no-python-downloads --no-project \
            "${BUNDLER}" \
            --repository-root "${ROOT}" \
            --output-root "${ROOT}/artifacts/processes" \
            "$@"
    fi
    printf '%s\n' "Process artifacts prepared in: ${ROOT}/artifacts/processes"
    printf '%s\n' "Create one .env beside each artifact pyproject.toml before local execution."
}

command_validate() {
    [[ "$#" -eq 0 ]] || fail "Usage: scripts/local-process.sh validate"
    validate_uv
    validate_artifacts
}

command_build() {
    local volume_mode="named"
    if [[ "${1:-}" == "--bind" ]]; then
        volume_mode="bind"
        shift
    fi
    [[ "$#" -eq 0 ]] || fail "Usage: scripts/local-process.sh build [--bind]"
    validate_uv
    validate_docker
    validate_artifacts
    if [[ -f "${COMPOSE_FILE}" ]]; then
        compose down --remove-orphans
    fi
    generate_workspace "${volume_mode}"
    compose build --no-cache
    compose config --services
}

command_up() {
    local volume_mode="named"
    if [[ "${1:-}" == "--bind" ]]; then
        volume_mode="bind"
        shift
    fi
    [[ "$#" -eq 0 ]] || fail "Usage: scripts/local-process.sh up [--bind]"
    validate_uv
    validate_docker
    validate_artifacts
    if [[ -f "${COMPOSE_FILE}" ]]; then
        compose down --remove-orphans
    fi
    generate_workspace "${volume_mode}"
    compose build --no-cache
    compose up -d
    compose ps -a
}

command_down() {
    [[ "$#" -eq 0 ]] || fail "Usage: scripts/local-process.sh down"
    validate_docker
    require_compose_file
    compose down --remove-orphans
}

command_ps() {
    [[ "$#" -eq 0 ]] || fail "Usage: scripts/local-process.sh ps"
    validate_docker
    require_compose_file
    compose ps -a
}

command_logs() {
    [[ "$#" -le 1 ]] || fail "Usage: scripts/local-process.sh logs [process]"
    validate_docker
    require_compose_file
    if [[ "$#" -eq 1 ]]; then
        compose logs -f "$1"
    else
        compose logs -f
    fi
}

command_run() {
    [[ "$#" -eq 1 ]] || fail "Usage: scripts/local-process.sh run <process>"
    validate_uv
    validate_docker
    validate_artifacts
    validate_workspace_contract
    local process="$1"
    compose config --services | grep -Fx -- "${process}" >/dev/null \
        || fail "Local Compose service not found: ${process}"
    compose run --rm "${process}" --run-once
}

case "${1:-}" in
    prepare)
        shift
        command_prepare "$@"
        ;;
    validate)
        shift
        command_validate "$@"
        ;;
    build)
        shift
        command_build "$@"
        ;;
    up)
        shift
        command_up "$@"
        ;;
    down)
        shift
        command_down "$@"
        ;;
    ps)
        shift
        command_ps "$@"
        ;;
    logs)
        shift
        command_logs "$@"
        ;;
    run)
        shift
        command_run "$@"
        ;;
    *)
        fail "Usage: scripts/local-process.sh {prepare [--scope SCOPE] --all|PROCESS [PROCESS ...]|validate|build [--bind]|up [--bind]|down|ps|logs [process]|run <process>}"
        ;;
esac

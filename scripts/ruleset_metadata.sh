#!/bin/bash

metadata_sidecar() {
    printf '%s.sources' "$1"
}

record_sources() {
    local target="$1"
    shift
    mkdir -p "$(dirname "$(metadata_sidecar "$target")")"
    printf '%s\n' "$@" | awk 'NF && !seen[$0]++' > "$(metadata_sidecar "$target")"
}

download_with_sources() {
    local url="$1"
    local target="$2"
    curl -fsSL "$url" > "$target" || return 1
    record_sources "$target" "$url"
}

merge_sources() {
    local target="$1"
    shift
    local source
    : > "$(metadata_sidecar "$target")"
    for source in "$@"; do
        if [[ -f "$(metadata_sidecar "$source")" ]]; then
            cat "$(metadata_sidecar "$source")" >> "$(metadata_sidecar "$target")"
        fi
    done
    sort -u "$(metadata_sidecar "$target")" -o "$(metadata_sidecar "$target")"
}

add_metadata_header() {
    local target="$1"
    local update_time="$2"
    local fallback_sources="$3"
    local source_file="$(metadata_sidecar "$target")"
    local temporary

    [[ -f "$source_file" && -s "$source_file" ]] || source_file="$fallback_sources"
    temporary=$(mktemp)
    awk '!/^# Updated: / && !/^# Sources:/ && !/^# - https?:\/\//' "$target" > "$temporary"
    {
        printf '# Updated: %s\n' "$update_time"
        printf '# Sources:\n'
        if [[ -f "$source_file" ]]; then
            sed 's/^/# - /' "$source_file"
        fi
        cat "$temporary"
    } > "$target"
    rm -f "$temporary"
}

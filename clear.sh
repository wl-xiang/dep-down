#!/bin/bash

print_help() {
    echo "Usage: $0 [OPTIONS] [DIRECTORIES...]"
    echo ""
    echo "Clear specified directories. If no directories are specified,"
    echo "clears wheels, packages, and node_modules by default."
    echo ""
    echo "Options:"
    echo "  -h, --help    Show this help message"
    echo ""
    echo "Available directories:"
    echo "  wheels         Clear ./wheels"
    echo "  packages       Clear ./packages"
    echo "  node_modules   Clear ./node_modules"
    echo "  tarballs       Clear ./tarballs"
    echo ""
    echo "Examples:"
    echo "  $0                    # Clear all default directories"
    echo "  $0 wheels             # Clear only wheels"
    echo "  $0 packages node_modules  # Clear packages and node_modules"
    exit 0
}

directories=()

while [[ "$#" -gt 0 ]]; do
    case "$1" in
        -h|--help)
            print_help
            ;;
        wheels|packages|node_modules)
            directories+=("$1")
            shift
            ;;
        *)
            echo "Error: Unknown argument: $1"
            print_help
            ;;
    esac
done

if [ ${#directories[@]} -eq 0 ]; then
    directories=("wheels" "packages" "node_modules" "tarballs")
fi

for dir in "${directories[@]}"; do
    dir_path="./$dir"
    if [ -d "$dir_path" ]; then
        rm -rf "$dir_path"/*
        echo "$dir directory cleared"
    else
        echo "$dir directory does not exist, skipped"
    fi
done

#!/bin/bash
# script copies essential repo documentation from a local repo directory
# 1. discovers the parent directory name
# 2. assigns name to srcrepo
# 3. sets the path from the current directory to the repo root
# 4. defines an array of files to copy
# 5. iteratively copies the files to the current directory

set -euo pipefail

# make script directory-safe: relative paths below assume cwd == script dir
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${script_dir}"

srcrepo="$(basename "$(pwd)")"
pathtoroot="../../../../${srcrepo}"

# confirm copy destination exists
if [ ! -d "${pathtoroot}" ]; then
    echo "Error: ${pathtoroot} does not exist"
    exit 1
fi

# confirm copy destination
read -p "Copy ${srcrepo} specs? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
fi

files=(
  "docs/specs/concept.md"
  "docs/specs/features.md"
  "docs/specs/tech-spec.md"
  "README.md"
)

for f in "${files[@]}"; do
  cp "${pathtoroot}/${f}" "${script_dir}/"
done

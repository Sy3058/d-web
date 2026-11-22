#!/bin/sh

if [ "$#" -ne 4 ]; then
  printf '%s\n' "usage: check-pr-target.sh BASE HEAD SOURCE_REPO TARGET_REPO" >&2
  exit 1
fi

base=$1
head=$2
source_repo=$3
target_repo=$4

if [ -z "$base" ] || [ -z "$head" ] || [ -z "$source_repo" ] || [ -z "$target_repo" ]; then
  printf '%s\n' "PR policy error: all arguments are required" >&2
  exit 1
fi

topic_pattern='^((be|fe|admin)/(feat|fix|chore|hotfix|refactor)|common/[a-z-]+)/.+$'

case "$base" in
  develop|main)
    if ! printf '%s\n' "$head" | grep -qE "$topic_pattern"; then
      printf '%s\n' "PR policy error: $base accepts only area-first topic branches" >&2
      exit 1
    fi
    ;;
  release)
    if [ "$head" != "develop" ]; then
      printf '%s\n' "PR policy error: release accepts only develop" >&2
      exit 1
    fi
    if [ "$source_repo" != "$target_repo" ]; then
      printf '%s\n' "PR policy error: release accepts develop only from the same repository" >&2
      exit 1
    fi
    ;;
  *)
    printf '%s\n' "PR policy error: unsupported base branch: $base" >&2
    exit 1
    ;;
esac

exit 0

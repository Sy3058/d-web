#!/bin/sh

set -eu

repo_root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
check_script=$repo_root/scripts/check-pr-target.sh
pre_push=$repo_root/.githooks/pre-push
prepare_commit_msg=$repo_root/.githooks/prepare-commit-msg
passed=0
failed=0

pass() {
  passed=$((passed + 1))
  printf 'ok %s - %s\n' "$passed" "$1"
}

fail() {
  failed=$((failed + 1))
  printf 'not ok - %s\n' "$1" >&2
}

expect_success() {
  name=$1
  shift
  if "$@" >/dev/null 2>&1; then
    pass "$name"
  else
    fail "$name"
  fi
}

expect_failure() {
  name=$1
  shift
  if "$@" >/dev/null 2>&1; then
    fail "$name"
  else
    pass "$name"
  fi
}

run_pre_push() {
  input=$1
  printf '%s\n' "$input" | "$pre_push" origin example.invalid
}

expect_success "topic PR to develop" "$check_script" develop be/feat/checkout fork/repo owner/repo
expect_success "common topic PR to develop" "$check_script" develop common/docs/release-policy owner/repo owner/repo
expect_success "transition topic PR to main" "$check_script" main fe/fix/viewer-scroll fork/repo owner/repo
expect_success "same-repository develop PR to release" "$check_script" release develop owner/repo owner/repo
expect_failure "topic PR to release" "$check_script" release be/feat/checkout owner/repo owner/repo
expect_failure "fork develop PR to release" "$check_script" release develop fork/repo owner/repo
expect_failure "release PR to develop" "$check_script" develop release owner/repo owner/repo
expect_failure "arbitrary branch PR to develop" "$check_script" develop feature/checkout owner/repo owner/repo
expect_failure "unknown base" "$check_script" staging be/feat/checkout owner/repo owner/repo
expect_failure "missing arguments" "$check_script" develop be/feat/checkout owner/repo
expect_failure "empty repository argument" "$check_script" develop be/feat/checkout '' owner/repo

zero=0000000000000000000000000000000000000000
one=1111111111111111111111111111111111111111
two=2222222222222222222222222222222222222222
expect_success "topic and tag push" run_pre_push "refs/heads/be/feat/checkout $one refs/heads/be/feat/checkout $zero
refs/tags/v1.0.0 $one refs/tags/v1.0.0 $zero"
expect_failure "differently named local ref to develop" run_pre_push "refs/heads/be/feat/checkout $one refs/heads/develop $zero"
expect_failure "protected branch deletion" run_pre_push "(delete) $zero refs/heads/release $one"
expect_failure "existing main update" run_pre_push "refs/heads/be/feat/checkout $one refs/heads/main $two"
expect_failure "existing develop update" run_pre_push "refs/heads/be/feat/checkout $one refs/heads/develop $two"
expect_failure "existing release update" run_pre_push "refs/heads/be/feat/checkout $one refs/heads/release $two"
expect_failure "mixed push cannot bypass protected ref" run_pre_push "refs/heads/be/feat/checkout $one refs/heads/be/feat/checkout $zero
refs/heads/other $one refs/heads/main $zero
refs/tags/v1.0.0 $one refs/tags/v1.0.0 $zero"

tmp_dir=$(mktemp -d)
trap 'rm -rf "$tmp_dir"' EXIT HUP INT TERM
git -C "$tmp_dir" init -q --initial-branch=fixture-base
git -C "$tmp_dir" config core.hooksPath /dev/null
git -C "$tmp_dir" config user.name BranchPolicyTest
git -C "$tmp_dir" config user.email test@example.invalid
git -C "$tmp_dir" commit -q --allow-empty -m initial
git -C "$tmp_dir" checkout -q --detach

expect_success "prepare hook allows detached HEAD" sh -c 'cd "$1" && "$2" message' sh "$tmp_dir" "$prepare_commit_msg"
git -C "$tmp_dir" checkout -q -b develop
expect_success "prepare hook allows develop" sh -c 'cd "$1" && "$2" message' sh "$tmp_dir" "$prepare_commit_msg"
git -C "$tmp_dir" checkout -q -b main
expect_success "prepare hook allows main" sh -c 'cd "$1" && "$2" message' sh "$tmp_dir" "$prepare_commit_msg"
git -C "$tmp_dir" checkout -q -b release
expect_success "prepare hook allows release" sh -c 'cd "$1" && "$2" message' sh "$tmp_dir" "$prepare_commit_msg"
git -C "$tmp_dir" checkout -q -b be/feat/valid-name
expect_success "prepare hook allows valid topic" sh -c 'cd "$1" && "$2" message' sh "$tmp_dir" "$prepare_commit_msg"
git -C "$tmp_dir" checkout -q -b invalid-name
expect_failure "prepare hook rejects invalid topic" sh -c 'cd "$1" && "$2" message' sh "$tmp_dir" "$prepare_commit_msg"

printf '1..%s\n' "$((passed + failed))"
printf '%s passed, %s failed\n' "$passed" "$failed"

if [ "$failed" -ne 0 ]; then
  exit 1
fi

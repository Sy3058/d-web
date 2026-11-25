#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

die() {
  echo "deployment failed: $*" >&2
  exit 1
}

if [[ $# -ne 2 ]]; then
  die "usage: deploy.sh staging|production COMMIT_SHA"
fi
readonly deploy_env=$1
readonly deploy_sha=$2
[[ $deploy_env == staging || $deploy_env == production ]] || die "invalid environment"
[[ $deploy_sha =~ ^[0-9a-f]{40}$ ]] || die "invalid commit SHA"

case $deploy_env in
  staging) readonly deploy_branch=develop deploy_project=dweb-staging ;;
  production) readonly deploy_branch=release deploy_project=dweb-production ;;
esac

readonly script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
readonly deploy_root=${DWEB_DEPLOY_ROOT:-$(dirname -- "$script_dir")}
readonly repo_file=$deploy_root/repository.url
readonly env_dir=$deploy_root/$deploy_env
readonly env_file=$env_dir/deploy.env
readonly source_repo=$deploy_root/source.git
readonly releases_dir=$env_dir/releases
readonly backups_dir=$deploy_root/backups/$deploy_env
readonly release_dir=$releases_dir/$deploy_sha
readonly edge_network=dweb-$deploy_env-edge

[[ -d $deploy_root && ! -L $deploy_root ]] || die "deployment root must be a real directory"
[[ -f $repo_file && ! -L $repo_file ]] || die "missing repository.url"
[[ -f $env_file && ! -L $env_file ]] || die "missing $deploy_env/deploy.env"
IFS= read -r repository_url < "$repo_file" || die "cannot read repository.url"
[[ $repository_url =~ ^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)(\.git)?$ ]] ||
  die "repository.url must be a public GitHub HTTPS URL"
readonly repo_owner=${BASH_REMATCH[1],,}
readonly repo_name=${BASH_REMATCH[2]%.git}
readonly expected_prefix=ghcr.io/$repo_owner/${repo_name,,}/$deploy_env

[[ -d $env_dir && ! -L $env_dir && ! -L $releases_dir && ! -L $deploy_root/backups && ! -L $backups_dir ]] ||
  die "symlinked deployment path refused"
mkdir -p -- "$releases_dir" "$backups_dir"

exec 9>"$deploy_root/.deploy.lock"
flock -w 1800 9 || die "another deployment still holds the global lock"

if [[ ! -e $source_repo ]]; then
  git clone --bare -- "$repository_url" "$source_repo"
fi
[[ -d $source_repo && ! -L $source_repo ]] || die "source.git must be a real bare repository"
[[ $(git -C "$source_repo" config --get remote.origin.url) == "$repository_url" ]] ||
  die "source.git origin differs from repository.url"
git -C "$source_repo" fetch --no-tags origin "refs/heads/$deploy_branch"
[[ $(git -C "$source_repo" rev-parse FETCH_HEAD) == "$deploy_sha" ]] ||
  die "requested SHA is not the current $deploy_branch head"

if [[ -e $release_dir ]]; then
  [[ -d $release_dir && ! -L $release_dir && -f $release_dir/deploy/runtime.yml ]] ||
    die "invalid existing release directory"
else
  readonly release_tmp=$releases_dir/.${deploy_sha}.tmp.$$
  [[ ! -e $release_tmp ]] || die "temporary release path already exists"
  mkdir -- "$release_tmp"
  git -C "$source_repo" archive "$deploy_sha" | tar -x -C "$release_tmp"
  [[ -f $release_tmp/deploy/runtime.yml && ! -L $release_tmp/deploy/runtime.yml ]] ||
    die "release lacks deploy/runtime.yml"
  mv -- "$release_tmp" "$release_dir"
fi

export DEPLOY_SHA=$deploy_sha RELEASE_SHA=$deploy_sha
readonly compose_file=$release_dir/deploy/runtime.yml
compose=(docker compose -p "$deploy_project" --env-file "$env_file" -f "$compose_file")
"${compose[@]}" config --quiet

current_config=$(mktemp "$env_dir/.config.XXXXXX.json")
other_config=
cleanup_private_configs() {
  rm -f -- "$current_config"
  [[ -z $other_config ]] || rm -f -- "$other_config"
}
trap cleanup_private_configs EXIT
"${compose[@]}" config --format json > "$current_config"
if [[ $deploy_env == staging ]]; then
  other_env=production
  other_project=dweb-production
else
  other_env=staging
  other_project=dweb-staging
fi
other_env_file=$deploy_root/$other_env/deploy.env
if [[ -e $other_env_file || -L $other_env_file ]]; then
  [[ -d $deploy_root/$other_env && ! -L $deploy_root/$other_env && -f $other_env_file && ! -L $other_env_file ]] ||
    die "invalid other-environment deploy.env path"
  other_config=$(mktemp "$env_dir/.other-config.XXXXXX.json")
  docker compose -p "$other_project" --env-file "$other_env_file" -f "$compose_file" \
    config --format json > "$other_config"
  python3 "$release_dir/deploy/scripts/check-isolation.py" "$deploy_env" "$current_config" "$other_config"
elif [[ $deploy_env == production ]]; then
  die "staging deploy.env is required before production bootstrap"
else
  python3 "$release_dir/deploy/scripts/check-isolation.py" "$deploy_env" "$current_config"
fi

"${compose[@]}" config --format json | DWEB_VALIDATE_ENV="$deploy_env" \
  DWEB_EXPECTED_PREFIX="$expected_prefix" DWEB_EDGE_NETWORK="$edge_network" \
  DWEB_EXPECTED_PROJECT="$deploy_project" python3 -c '
import json, os, sys
c=json.load(sys.stdin)
env=os.environ["DWEB_VALIDATE_ENV"]
sha=os.environ["DEPLOY_SHA"]
prefix=os.environ["DWEB_EXPECTED_PREFIX"]
edge=os.environ["DWEB_EDGE_NETWORK"]
project=os.environ["DWEB_EXPECTED_PROJECT"]
if c.get("name") != project:
    raise SystemExit("invalid compose project")
services=c.get("services", {})
for name in ("api", "frontend", "admin"):
    s=services.get(name, {})
    if s.get("image") != f"{prefix}/{name}:{sha}":
        raise SystemExit(f"invalid {name} image namespace")
    if s.get("ports"):
        raise SystemExit(f"published ports forbidden for {name}")
if services.get("migrate", {}).get("image") != services.get("api", {}).get("image"):
    raise SystemExit("migrate must use the API image")
postgres=services.get("postgres", {})
if postgres.get("ports"):
    raise SystemExit("published postgres ports forbidden")
postgres_networks=postgres.get("networks", {})
postgres_network_keys=set(postgres_networks if isinstance(postgres_networks, dict) else postgres_networks)
if postgres_network_keys - {"default"}:
    raise SystemExit("postgres must only use the project default network")
api_env=services.get("api", {}).get("environment", {})
if env == "staging" and api_env.get("PAYMENT_ENVIRONMENT") != "test":
    raise SystemExit("staging PAYMENT_ENVIRONMENT must be test")
networks=c.get("networks", {})
other_env="production" if env=="staging" else "staging"
if any(v.get("name")==f"dweb-{other_env}-edge" for v in networks.values() if isinstance(v,dict)):
    raise SystemExit("other environment edge network forbidden")
edge_defs=[v for v in networks.values() if isinstance(v, dict) and v.get("name")==edge]
if len(edge_defs) != 1 or not edge_defs[0].get("external"):
    raise SystemExit("invalid external edge network")
for name in ("api", "frontend", "admin"):
    attached=services[name].get("networks", {})
    entries=attached.items() if isinstance(attached, dict) else ((n,{}) for n in attached)
    matches=[cfg or {} for key,cfg in entries if networks.get(key,{}).get("name")==edge]
    if len(matches)!=1 or matches[0].get("aliases", []) != [f"{env}-{name}"]:
        raise SystemExit(f"invalid {name} edge alias")
volumes=c.get("volumes", {})
if volumes.get("postgres_data", {}).get("name") != f"{project}_postgres_data":
    raise SystemExit("invalid postgres volume name")
'

api_base_url=$("${compose[@]}" config --format json | python3 -c '
import json, sys
value=json.load(sys.stdin).get("services",{}).get("api",{}).get("environment",{}).get("API_BASE_URL","")
if not isinstance(value, str) or not value.startswith("https://"):
    raise SystemExit("invalid API_BASE_URL")
print(value)
')
readonly api_base_url

if ! docker network inspect "$edge_network" >/dev/null 2>&1; then
  docker network create "$edge_network" >/dev/null
fi
[[ $(docker network inspect --format '{{.Name}}' "$edge_network") == "$edge_network" ]] ||
  die "edge network validation failed"

"${compose[@]}" pull postgres api frontend admin
declare -A pinned_images
for service in api frontend admin; do
  image=$expected_prefix/$service:$deploy_sha
  repo_digests=$(docker image inspect --format '{{json .RepoDigests}}' "$image")
  pinned_image=$(python3 -c '
import json,re,sys
repo=sys.argv[1]
try: values=json.load(sys.stdin)
except json.JSONDecodeError: raise SystemExit("invalid RepoDigests JSON")
matches=[v for v in values if re.fullmatch(re.escape(repo)+r"@sha256:[0-9a-f]{64}",v)]
if len(matches)!=1: raise SystemExit("expected exactly one repository digest")
print(matches[0])
' "$expected_prefix/$service" <<< "$repo_digests") || die "$service image has no unique trusted repository digest"
  pinned_images[$service]=$pinned_image
  revision=$(docker image inspect --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "$pinned_image")
  [[ $revision == "$deploy_sha" ]] || die "$service image revision does not match requested SHA"
done
for service in frontend admin; do
  image_api_url=$(docker image inspect --format '{{ index .Config.Labels "io.dweb.api-url" }}' "${pinned_images[$service]}")
  [[ $image_api_url == "$api_base_url" ]] || die "$service image API URL differs from runtime API_BASE_URL"
done

lock_file=$release_dir/images.lock.json
lock_tmp=$(mktemp "$release_dir/.images.lock.json.XXXXXX")
python3 -c '
import json,sys
api,frontend,admin,path=sys.argv[1:]
data={"services":{
  "api":{"image":api,"pull_policy":"never"},
  "migrate":{"image":api,"pull_policy":"never"},
  "frontend":{"image":frontend,"pull_policy":"never"},
  "admin":{"image":admin,"pull_policy":"never"},
}}
with open(path,"w",encoding="utf-8") as f:
    json.dump(data,f,separators=(",",":"),sort_keys=True)
    f.write("\n")
' "${pinned_images[api]}" "${pinned_images[frontend]}" "${pinned_images[admin]}" "$lock_tmp"
chmod 600 "$lock_tmp"
mv -- "$lock_tmp" "$lock_file"
compose=(docker compose -p "$deploy_project" --env-file "$env_file" -f "$compose_file" -f "$lock_file")
"${compose[@]}" config --quiet

"${compose[@]}" up -d --pull never --wait --wait-timeout 180 postgres
readonly backup_stamp=$(date -u +%Y%m%dT%H%M%SZ)
readonly backup_file=$backups_dir/before-$deploy_sha-$backup_stamp.dump.gz
readonly backup_tmp=$backup_file.tmp
if ! "${compose[@]}" exec -T postgres pg_dump -U dweb -d dweb -Fc | gzip -c > "$backup_tmp"; then
  rm -f -- "$backup_tmp"
  die "database backup failed; migration was not attempted"
fi
[[ -s $backup_tmp ]] || die "database backup was empty"
chmod 600 "$backup_tmp"
mv -- "$backup_tmp" "$backup_file"

"${compose[@]}" stop api
"${compose[@]}" run --rm --no-deps --pull never migrate
"${compose[@]}" up -d --no-deps --pull never --wait --wait-timeout 180 api frontend admin

current_file=$env_dir/current.sha
previous_file=$env_dir/previous.sha
[[ ! -L $current_file && ! -L $previous_file ]] || die "symlinked deployment state refused"
old_sha=
if [[ -f $current_file && ! -L $current_file ]]; then
  IFS= read -r old_sha < "$current_file" || true
fi
if [[ $old_sha =~ ^[0-9a-f]{40}$ && $old_sha != "$deploy_sha" ]]; then
  previous_tmp=$(mktemp "$env_dir/.previous.sha.XXXXXX")
  printf '%s\n' "$old_sha" > "$previous_tmp"
  mv -- "$previous_tmp" "$previous_file"
fi
current_tmp=$(mktemp "$env_dir/.current.sha.XXXXXX")
printf '%s\n' "$deploy_sha" > "$current_tmp"
mv -- "$current_tmp" "$current_file"
echo "deployment healthy: $deploy_env $deploy_sha"

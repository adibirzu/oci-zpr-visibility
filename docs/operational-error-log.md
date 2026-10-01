# Operational errors and resolutions — October 1, 2026

This is a sanitized operator note. It contains no tenant/resource identifiers,
private addresses, saved plans or raw provider output.

| Error / symptom | Cause | Resolution / current status |
|---|---|---|
| `oci iam tenancy get` reports required `--tenancy-id` missing | This OCI CLI command does not infer the tenancy OCID from profile `DEFAULT`. | Read the configured profile's tenancy value internally and pass it explicitly. Do not copy that value into documentation or terminal receipts. |
| A compartment lookup returned `InvalidParameter` and the tenancy variable was empty | The OCI config uses whitespace around `tenancy = ...`; an anchored `tenancy=` parser did not match it. | Parse key/value fields without printing credential values, then pass the resolved tenancy internally to the scoped lookup. |
| OCI CLI JMESPath rejected `display-name` as an unknown token | Hyphenated OCI response keys require quoted identifiers. | Query `"display-name"` and similarly quote `"lifecycle-state"`; validate filters with local `--help`/read-only calls before using the result. |
| New archive tests failed when launched with system `python3` | The machine's system interpreter is Python 3.9, below the project's declared `>=3.10` minimum; helpers use PEP 604 type syntax. | Run project and packaging gates with Python 3.11, matching CI. |
| Packer validation reported a required Oracle plugin missing | The plugin had been initialized into a private directory that was not supplied to the validate process. | Set `PACKER_PLUGIN_PATH` to that exact directory for `packer validate`; template validation then passed without launching OCI resources. |
| Python `ConfigParser.has_section("DEFAULT")` is false for the special default section | `DEFAULT` is parsed as `ConfigParser.defaults()`, not as an ordinary section. | Use `.defaults()` for the OCI config's default profile and keep its credential values out of stdout. |
| `resource-manager job create-plan-job` rejects `--execution-plan-strategy` | That CLI option belongs to apply/destroy jobs, not plan-job creation. | Create the plan job without a strategy; use `FROM_PLAN_JOB_ID` only on the subsequent apply/destroy job. |
| RM plan's lifecycle precondition says OCI CLI is available but Resource Principal is unavailable | Resource Manager's Terraform worker did not expose authenticated CLI Resource Principal context to the external/local-exec process. The plan calculated 5 adds, 5 changes and 4 destroys, then failed closed. | Removed `hashicorp/external` and all job-side CLI hooks. Verify readiness and perform ownership-checked cleanup from an operator machine using a named OCI CLI profile and the sensitive lifecycle output. The corrected-source plan succeeded; no apply was run. |
| `oci resource-manager stack update --config-source file://...` cannot resolve the local ZIP | `--config-source` expects a local ZIP path for this stack source update, not the OCI CLI `file://` complex-parameter convention. | Pass the absolute local ZIP path. Re-read the exact named stack and require `ACTIVE`/`ZIP_UPLOAD` before updating; then create a fresh plan. |
| pip warns that the default user cache is unwritable in the managed macOS workspace | The home cache path is owned/protected by the environment. pip disables its cache automatically; the wheel download still completed. | Set `PIP_NO_CACHE_DIR=1` for the isolated Linux wheelhouse/build. No privilege escalation is needed. |
| The initial image inventory marked the project wheel and `wheel` package license as `REVIEW_REQUIRED` | The project had no explicit license declaration, and wheel is a packaging-only tool rather than a runtime dependency. | Added the Apache-2.0 project license metadata/file, moved setuptools/wheel into a build-only lock, and made image packaging fail when any component has no license metadata. The regenerated bundle reports zero missing license metadata; publisher legal review remains required. |
| Directly importing `build_image_bundle.py` in pytest could not find `build_collector_archive` | The script assumed Python's command-line script directory was on `sys.path`, which is not true for importlib-based tests. | Made the image payload descriptor allowlist explicit in the builder; its asset allowlist test passes and excludes Packer/install scripts and bytecode caches. |
| Packer checksum verification reported the downloaded archive missing | `shasum --check` resolved the checksum manifest's filename relative to the repository working directory, not the download directory. | Run checksum verification from the private download directory and map the manifest filename to the locally saved archive name. Packer 1.16.1/plugin 1.1.2 then validated without OCI access. |

The failed plan is not an apply failure: it made no infrastructure changes.
The latest source-matched plan for ZIP SHA-256
`27bbf67600b763c7fe90444274fc7fb7f4bb9105f3de63ab0439097714eb5039` succeeded
with 5 adds, 5 changes and 4 destroys. It remains unapplied and needs exact-
plan review and approval before any apply.

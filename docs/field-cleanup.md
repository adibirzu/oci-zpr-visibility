# Log Analytics field cleanup

Fields are tenancy-wide shared content. No-value results, old update times,
or absent parser references alone do not establish a safe deletion candidate.

## Read-only inventory

```bash
python3.11 scripts/audit_la_fields.py --profile <PROFILE> --region <REGION> \
  --person '<IDENTITY_KEYWORDS>' --output <NEW_PRIVATE_OUTPUT_JSON>
```

The tool saves definitions, identity matches and provider usage results as a
mode-0600 file. Keep it outside the repository. It never deletes, infers
creators, or labels a field deletion-ready. Creator identity is not present in
the field model; `time_updated` does not mean `time_created`.

For each possible deletion, require:

1. A successful creation Audit event tied to the exact field and intended
   account. An upsert/update event identifies a writer, not necessarily creator.
2. Fresh `get_field_usages` with no dependent parsers or sources.
3. A complete saved-search and dashboard reference scan in the tenancy subtree.
   Keep uncertain references; any unavailable inventory blocks deletion.
4. No pending-installation, ownership-manifest, Terraform, or release dependency.
5. A private definition export and reviewed exact deletion set. Creating a new
   field later may allocate a different internal name; the export is not an
   automatic rollback of historical field associations.
6. Fresh tenancy-bound preflight and destructive-action preview/approval through
   the OCI skills action wrapper. Recheck dependencies and etag immediately before
   each delete; read back absence and revalidate dependent content afterward.

Management Dashboard APIs can throttle parallel reads. Use paced requests and
bounded retries, retaining completed results. Audit scans should be bounded and
checkpointed; historical ownership may be unavailable outside retained Audit
coverage. Log Analytics `Original Log Content` query output can be truncated;
do not treat a partial JSON record as complete creator/field evidence. The
virtual field is not accepted by EXTRACT or EVAL in the inspected service;
use verified parser fields or original provider Audit records instead.

## October 1, 2026 provider-verified inventory

- 1,098 custom fields inspected; all field-usage reads completed.
- 971 have parser/source references; 127 have none.
- 81 of those 127 are protected pending ZPR installation fields.
- 46 remaining candidates are numeric or timestamp fields, not STRING fields.
- 814 saved searches and 209 dashboards inspected: five candidates have detected
  content references, leaving 41 without detected parser/source/search/dashboard
  references. This is not creator attribution or proof of no historical data.
- No fields deleted. Creator provenance remains required before cleanup.

Bounded provider Audit reads around the ten recent candidates' update times
found successful UpsertField events for all ten, written by three resolved
accounts that did not match the selected operator or the two resolved requested
accounts. This establishes writers, not necessarily original creators. The
other 31 candidates predate the standard one-year Audit window; archived
evidence is needed for creator attribution. No current identity matched the
remaining requested name or checked spelling variants. A subsequent check using
the corrected name searched legacy IAM names/descriptions/emails and all three
returned active Identity Domains, using paginated SCIM user-name, display-name,
and family-name filters. All checks completed with zero matching accounts and
zero matches to the cached field-mutation actors. An exact OCI username/email
or archived identity evidence is required to continue attribution; this result
does not prove the person never held an account or created fields.

Minute-scale windows with page/time limits and checkpointed receipts completed
this check. An initial full-hour scan was stopped because broad pagination was
too slow. Raw field definitions and Audit receipts remain private and outside
tracked source.

Deleting numeric/timestamp candidates does not release single-valued STRING
capacity. The ZPR provisioning repair reuses native Operation/Category fields
and a LONG occurrence count; it does not depend on deleting shared content.

Official API: [field usages](https://docs.oracle.com/en-us/iaas/tools/python-sdk-examples/latest/loganalytics/get_field_usages.py.html).

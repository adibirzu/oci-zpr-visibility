#!/usr/bin/env python3
"""Render a local, sanitized read-only estate snapshot; never calls OCI.

Inputs contain private inventory/flow data. Output uses opaque per-file aliases
and aggregates. It is a timestamped snapshot, not a polling provider console.
"""
import argparse
import collections
import json
from datetime import datetime, timezone
from pathlib import Path


def review_data(snapshot, flows, flow_summary, dashboard_report=None):
    aliases = {}

    def alias(value, family):
        if not value:
            return 'Not reported'
        key = (family, str(value))
        if key not in aliases:
            aliases[key] = f'{family} {sum(k[0] == family for k in aliases) + 1}'
        return aliases[key]

    rows = []
    for resource in snapshot.get('resource_inventory', []):
        family = resource.get('resource_type', 'unknown')
        rows.append({
            'name': alias(resource.get('resource_id'), family),
            'family': family,
            'state': resource.get('lifecycle_state') or 'Not reported',
            'protection': resource.get('protection_status') or 'Not reported',
            'scope': alias(resource.get('compartment_id'), 'Scope'),
            'vcn': alias(resource.get('vcn_id'), 'VCN'),
            'subnet': alias(resource.get('subnet_id'), 'Subnet'),
        })
    paths = collections.Counter()
    for flow in flows:
        data = flow.get('data', flow)
        paths[(alias(data.get('sourceAddress'), 'Endpoint'),
               alias(data.get('destinationAddress'), 'Endpoint'),
               data.get('action', 'UNKNOWN'), str(data.get('destinationPort', '?')))] += 1
    def observed_time(value):
        try:
            parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
            if parsed.tzinfo is None:
                return None, 'UNAVAILABLE'
            age = (datetime.now(timezone.utc) - parsed).total_seconds() / 60
            return parsed.isoformat(), 'FRESH' if 0 <= age <= 60 else 'STALE_OR_CLOCK_SKEW'
        except (ValueError, TypeError):
            return None, 'UNAVAILABLE'

    timestamp, freshness = observed_time(snapshot.get('snapshot_time'))
    flow_time, flow_freshness = observed_time(flow_summary.get('retrieved_at'))
    actions = collections.Counter()
    for flow in flows:
        action = flow.get('data', flow).get('action', 'UNKNOWN')
        actions[action if action in {'ACCEPT', 'REJECT'} else 'UNKNOWN'] += 1
    count_matches = flow_summary.get('flow_records') == len(flows)
    lab = [resource for resource in snapshot.get('resource_inventory', [])
           if resource.get('resource_type') == 'instance' and resource.get('resource_name') in
           {'zpr-visibility-controller', 'zpr-visibility-web', 'zpr-visibility-db'}]
    lab_running = sum(resource.get('lifecycle_state') == 'RUNNING' for resource in lab)
    heartbeat_time, _ = observed_time(flow_summary.get('native_heartbeat_observed_at'))
    heartbeat_count = flow_summary.get('native_heartbeat_count')
    heartbeat_count = heartbeat_count if type(heartbeat_count) is int and heartbeat_count >= 0 else None
    native = {'dashboards': [], 'observed_at': None, 'indexed_records': None}
    if isinstance(dashboard_report, dict):
        native['observed_at'], _ = observed_time(dashboard_report.get('observed_at'))
        native['indexed_records'] = dashboard_report.get('indexed_records') if type(dashboard_report.get('indexed_records')) is int else None
        allowed_names = {'Executive posture', 'Policy inventory', 'Protected resource map', 'Resource estate',
                         'Allow block traffic', 'Drift governance', 'Detections', 'Collection health'}
        for row in dashboard_report.get('dashboards', []):
            if not isinstance(row, dict) or row.get('name') not in allowed_names:
                continue
            safe = {'name': row['name'], 'status': row.get('status') if row.get('status') in {'UPDATED', 'ADDED'} else 'UNVERIFIED'}
            for key in ('widgets', 'data', 'zero_allowed', 'zero_unexpected', 'errors'):
                value = row.get(key)
                safe[key] = value if type(value) is int and value >= 0 else None
            native['dashboards'].append(safe)
    return {
        'native': native,
        'native_health': {'count': heartbeat_count, 'observed_at': heartbeat_time},
        'time': timestamp,
        'freshness': freshness,
        'lab': {'observed': len(lab), 'running': lab_running,
                'status': 'OBSERVED' if lab and freshness == 'FRESH' else 'STALE_OR_UNAVAILABLE'},
        'resources': rows,
        'operational_count': sum(row['state'] not in {'DELETED', 'TERMINATED', 'DELETING', 'TERMINATING'} for row in rows),
        'flows': [{'source': key[0], 'destination': key[1], 'action': key[2],
                   'port': key[3], 'records': value} for key, value in paths.items()],
        'flowSummary': {'flow_records': len(flows), 'actions': dict(actions),
                        'window_minutes': flow_summary.get('window_minutes') if isinstance(flow_summary.get('window_minutes'), int) else None,
                        'retrieved_at': flow_time, 'freshness': flow_freshness,
                        'status': 'OBSERVED' if count_matches and flow_freshness == 'FRESH' else 'STALE_OR_INVALID'},
        'coverage': [{key: row.get(key) for key in
                      ('resource_type', 'coverage_status', 'eligible_count', 'protected_count', 'available_count')}
                     for row in snapshot.get('resource_coverage', [])],
        'errors': snapshot.get('collection_error_count', 0),
    }


HTML = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ZPR estate • provider snapshot</title>
<style>
:root{--red:#C74634;--ink:#312d2a;--paper:#f6f4f1;--line:#d9d4ce;--green:#39784b;--blue:#287fa8}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 system-ui,sans-serif}header{background:#312d2a;color:white;padding:18px 5vw;border-top:5px solid var(--red)}header small{color:#d3ccc4}main{max-width:1280px;margin:auto;padding:30px 4vw}h1{font-size:32px;line-height:1.2;margin:0 0 12px}h2{font-size:20px;margin:0 0 14px}.muted{color:#69615a}p{max-width:80ch}.meta{display:flex;gap:15px;flex-wrap:wrap;font-size:13px}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px}.panel{background:white;border:1px solid var(--line);padding:22px;margin-bottom:20px;min-width:0;overflow-wrap:anywhere}.stat{font-size:36px;font-weight:650;display:block;line-height:1.3}.pill{display:inline-block;border:1px solid var(--line);padding:2px 8px;border-radius:4px;font-size:12px}.ok{color:var(--green)}.hold{color:#985f00}.tabs{display:flex;gap:4px;flex-wrap:wrap;margin:24px 0 18px;border-bottom:1px solid var(--line)}button{font:inherit;cursor:pointer;background:white;border:1px solid var(--line);padding:9px 16px;color:var(--ink)}button[aria-selected=true]{border-bottom:3px solid var(--red);font-weight:650}.tools{display:flex;gap:12px;flex-wrap:wrap;margin:10px 0 18px}select,input{font:inherit;padding:9px;border:1px solid var(--line);max-width:100%;background:white}label{display:flex;gap:8px;align-items:center}.scroll{overflow:auto;max-width:100%}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:11px 13px;text-align:left;border-bottom:1px solid var(--line);overflow-wrap:anywhere}th{font-weight:600;background:var(--paper)}.bar{height:16px;display:flex;background:#ddd;overflow:hidden;margin:12px 0}.accept{background:var(--green)}.reject{background:var(--red)}[hidden]{display:none!important}code{font-size:13px;overflow-wrap:anywhere}.two{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}.two>*{min-width:0}.notice{border-left:4px solid #aa7620}.evidence{font-size:13px;line-height:1.8}footer{font-size:12px;margin-top:20px;color:#69615a}details{margin:15px 0}summary{cursor:pointer;font-weight:600}@media(max-width:800px){.grid,.two{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:500px){.grid,.two{grid-template-columns:minmax(0,1fr)}main{padding:22px 16px}h1{font-size:26px}}
</style></head><body><header><strong>OCI ZPR Visibility</strong> <small> / Local estate review</small></header><main>
<h1>Inventory and observed traffic snapshot.</h1><p class="muted">OCI inventory and Logging query results supplied to a local renderer. Resource identifiers and addresses are replaced with aliases. This page is a fixed snapshot; reload does not query OCI.</p><div class="meta"><span id="timestamp"></span><span id="freshness" class="pill"></span><span class="pill">Independent accelerator</span></div>
<div class="grid" style="margin-top:24px"><div class="panel">Lab VMs<span id="labcount" class="stat"></span><span id="labstatus"></span></div><div class="panel">Observed estate<span id="total" class="stat"></span>Resource observations, including terminal states</div><div class="panel">Flow records<span id="flowcount" class="stat"></span><span id="flowwindow"></span></div><div class="panel">Collection errors<span id="errors" class="stat"></span>Explicit compartment scope</div></div>
<div class="panel notice"><strong id="nativetitle">Native dashboard evidence</strong><p id="nativestatus"></p><p>Scheduled controller refresh and authenticated OCI browser rendering require separate verification. Successful flow capture does not prove application connectivity or a ZPR enforcement verdict.</p></div>
<nav class="tabs" aria-label="Evidence views"><button aria-selected="true" data-tab="estate">Resource estate</button><button aria-selected="false" data-tab="traffic">Observed traffic</button><button aria-selected="false" data-tab="coverage">Collection coverage</button><button aria-selected="false" data-tab="delivery">ORM & next views</button></nav>
<section id="estate" class="panel"><h2>Latest observed resources</h2><p class="muted">Compute, VCNs, OKE clusters and node pools, Autonomous Databases. ACTIVE and RUNNING describe provider lifecycle only.</p><div class="tools"><label>Family <select id="family"><option value="">All families</option></select></label><label>State <select id="state"><option value="">All states</option></select></label><label>Find <input id="search" placeholder="Filter aliases or scope"></label></div><p id="resultcount" class="muted"></p><div class="scroll"><table><thead><tr><th>Resource alias</th><th>Lifecycle</th><th>Protection evidence</th><th>Scope / placement</th></tr></thead><tbody id="inventory"></tbody></table></div></section>
<section id="traffic" class="panel" hidden><h2>Real traffic from the existing lab flow log</h2><p>Source: OCI Logging • selected endpoint subnet flow log • 15-minute window. Counts are flow records, not requests, unique connections, or ZPR decisions.</p><div class="bar" aria-hidden="true"><div id="acceptbar" class="accept"></div><div id="rejectbar" class="reject"></div></div><p id="actions"></p><div class="scroll"><table><thead><tr><th>Source alias</th><th>Destination alias</th><th>Port</th><th>Observed action</th><th>Records</th></tr></thead><tbody id="paths"></tbody></table></div><p class="evidence">ACCEPT/REJECT is the VCN Flow Log action. Attribution to ZPR requires independent policy and network evidence. Endpoint aliases identify addresses within this snapshot only.</p></section>
<section id="coverage" class="panel" hidden><h2>Collected, partial, and unimplemented resource families</h2><p class="muted">A collected zero is distinct from NOT_COLLECTED. OKE attribute evidence may be unavailable in the installed SDK; parent VCN attributes are never inherited.</p><div class="scroll"><table><thead><tr><th>Family</th><th>Coverage</th><th>Eligible</th><th>With attributes</th><th>Available lifecycle</th></tr></thead><tbody id="coverageRows"></tbody></table></div></section>
<section id="delivery" hidden><div class="two"><div class="panel"><h2>Existing VCN in ORM</h2><p><code>network_mode = existing</code> selects a supplied VCN and subnet. Collection scopes and existing flow-log references are explicit.</p><p>Observation mode creates no demo VCN, routes, security lists, endpoints, attributes, or demo ZPR policy. Private controller placement is the default; OCI API/bootstrap egress must already exist.</p><p class="hold">Switching an existing lab stack to this mode would plan removal of lab-owned resources. Use a separate observer stack and review its saved plan.</p><p class="evidence">Code-backed local changes. New source has not been applied to the live stack. Existing IAM read grants remain broad; review before deployment.</p></div><div class="panel"><h2>Dashboard expansion</h2><p>Added native estate widgets for lifecycle by family, placement, protection evidence, collection gaps and snapshot freshness.</p><ul><li>Next: observed path matrix with VCN/subnet identity.</li><li>Next: OKE API endpoint versus node/pod VNIC coverage.</li><li>Next: ADB availability beside client-side connection evidence.</li><li>Next: load balancer backend health and denied-path investigations.</li><li>Next: last successful refresh and time-window warnings.</li></ul><p class="evidence">Additional integrations are proposed, not deployed. OKE health needs node readiness; database health needs authenticated database probes.</p></div></div></section>
<section class="panel"><h2>Native dashboard update receipts</h2><p id="nativequerytime" class="muted"></p><p>The new Resource estate dashboard contains lifecycle by family, resource placement, protection evidence, collection gaps, snapshot freshness, and lifecycle totals. DATA means the stored query returned rows; allowed zero results can represent no findings or drift.</p><div class="scroll"><table><thead><tr><th>Dashboard</th><th>Update</th><th>Widgets</th><th>With data</th><th>Allowed zero</th><th>Unexpected zero / errors</th></tr></thead><tbody id="nativeRows"></tbody></table></div><p class="evidence">Read-only OCI API checks supplied to this local snapshot. These receipts are not screenshots of the authenticated OCI console. Manual evidence upload does not establish recurring refresh.</p></section>
<footer>Design follows the project's existing OCI dashboard surface: neutral panels, dark navigation, Redwood red, and restrained status colors. Local-only review; no cloud mutation controls.</footer></main>
<script type="application/json" id="evidence">__DATA__</script><script>
const data=JSON.parse(document.getElementById('evidence').textContent);const el=id=>document.getElementById(id);const text=(id,value)=>el(id).textContent=value;const dash=v=>v===null||v===undefined?'Unavailable':v;function cell(row,value){const c=document.createElement('td');c.textContent=dash(value);row.append(c)}
text('timestamp','Inventory observed '+(data.time||'Unavailable'));text('freshness',data.freshness);text('labcount',data.lab.running+' / '+data.lab.observed);text('labstatus','Last observed RUNNING • '+data.lab.status);text('total',data.resources.length);text('flowcount',data.flowSummary.flow_records);text('flowwindow','Window: '+(data.flowSummary.window_minutes||'Unavailable')+' minutes • '+data.flowSummary.status+' • queried '+(data.flowSummary.retrieved_at||'Unavailable'));text('errors',data.errors);
text('nativetitle',data.native.dashboards.length?'Native dashboards updated • provider API receipts':'Native dashboard update evidence unavailable');text('nativestatus',data.native.dashboards.length?(data.native.dashboards.length+' dashboard receipts • '+dash(data.native.indexed_records)+' indexed current-run records. Estate fields, parser and source updated; fresh inventory and observed traffic uploaded manually.'):'No dashboard update receipt was supplied.');text('nativequerytime','Verified at '+(data.native.observed_at||'Unavailable'));
for(const r of data.native.dashboards){const tr=document.createElement('tr');[r.name,r.status,r.widgets,r.data,r.zero_allowed,dash(r.zero_unexpected)+' / '+dash(r.errors)].forEach(v=>cell(tr,v));el('nativeRows').append(tr)}
for(const [id,key] of [['family','family'],['state','state']])for(const value of [...new Set(data.resources.map(r=>r[key]))].sort()){const o=document.createElement('option');o.value=value;o.textContent=value;el(id).append(o)}
function render(){const rows=data.resources.filter(r=>(!el('family').value||r.family===el('family').value)&&(!el('state').value||r.state===el('state').value)&&JSON.stringify(r).toLowerCase().includes(el('search').value.toLowerCase()));el('inventory').replaceChildren();for(const r of rows){const tr=document.createElement('tr');cell(tr,r.name);cell(tr,r.state);cell(tr,r.protection);cell(tr,[r.scope,r.vcn,r.subnet].filter(v=>v!=='Not reported').join(' / '));el('inventory').append(tr)}text('resultcount',rows.length+' resources shown of '+data.resources.length)}['family','state','search'].forEach(id=>el(id).addEventListener('input',render));render();
const a=data.flowSummary.actions||{};const total=Math.max(data.flowSummary.flow_records,1);el('acceptbar').style.width=(a.ACCEPT||0)/total*100+'%';el('rejectbar').style.width=(a.REJECT||0)/total*100+'%';text('actions',(a.ACCEPT||0)+' ACCEPT records • '+(a.REJECT||0)+' REJECT records');for(const r of data.flows){const tr=document.createElement('tr');[r.source,r.destination,r.port,r.action,r.records].forEach(v=>cell(tr,v));el('paths').append(tr)}for(const r of data.coverage){const tr=document.createElement('tr');[r.resource_type,r.coverage_status,r.eligible_count,r.protected_count,r.available_count].forEach(v=>cell(tr,v));el('coverageRows').append(tr)}
document.querySelectorAll('[data-tab]').forEach(button=>button.addEventListener('click',()=>{document.querySelectorAll('[data-tab]').forEach(b=>b.setAttribute('aria-selected',String(b===button)));['estate','traffic','coverage','delivery'].forEach(id=>el(id).hidden=id!==button.dataset.tab)}));
</script></body></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', required=True, type=Path)
    parser.add_argument('--flows', required=True, type=Path)
    parser.add_argument('--flow-summary', required=True, type=Path)
    parser.add_argument('--dashboard-report', type=Path)
    parser.add_argument('--output', type=Path, default=Path('.lavish/estate-review.html'))
    args = parser.parse_args()
    evidence = review_data(json.loads(args.snapshot.read_text()), json.loads(args.flows.read_text()),
                           json.loads(args.flow_summary.read_text()),
                           json.loads(args.dashboard_report.read_text()) if args.dashboard_report else None)
    encoded = json.dumps(evidence).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(HTML.replace('__DATA__', encoded))
    print(f'Local snapshot review: {args.output}')


if __name__ == '__main__':
    main()

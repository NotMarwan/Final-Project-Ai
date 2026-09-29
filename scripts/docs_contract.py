"""Generate the current documentation contract from local implementation.

Standard library only. --check is read-only; --write refreshes derived files.
It does not certify runtime correctness or silently pass acceptance gates.
"""
from __future__ import annotations
import argparse
import hashlib
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ('docs/SOURCE-MANIFEST.json', 'docs/design-tokens.json', 'docs/DESIGN.md', 'docs/design-preview.html', 'docs/CURRENT.md')
BLUEPRINT_INDEX = 'docs/blueprint/index.json'
BLUEPRINT_VIEW = 'docs/blueprint/INDEX.md'
STATUSES = ('implemented-active', 'partial', 'disconnected', 'proposed', 'unverified')
KIND_ID = {'runtime': re.compile(r'F-\d{2}$'), 'ui': re.compile(r'U-\d{2}$'), 'contract': re.compile(r'SC-\d+$'),
           'slice': re.compile(r'S-\d{2}$'), 'finding': re.compile(r'[BNR]-\d+$')}
ID_SCAN = re.compile(r'\b(?:F-\d{2}|U-\d{2}|SC-\d+|S-\d{2}|B-\d+|N-\d+|R-\d)\b')
SCAN_DOCS = ('docs/CURRENT.md', 'docs/PLAN.md', 'docs/DESIGN.md', 'docs/ISSUES.md', 'docs/RUNBOOK.md', 'docs/MAINTENANCE.md')
ENTRY_FIELDS = ('id', 'title', 'kind', 'status', 'source_refs', 'tests', 'evidence', 'limitations')
BACKEND_SOURCE_EXCLUSIONS = frozenset(('tests', 'tools', 'archive', '__pycache__', 'احتياطي'))
MOJIBAKE_MARKERS = ('\ufffd', 'â€“', 'â€”', 'â‰¥', 'â‰¤', 'آ±', 'آ§')

def digest(data):
    return hashlib.sha256(data).hexdigest()

def source_digest(path):
    # Git's Windows checkout line endings must not create false design drift.
    return digest(path.read_bytes().replace(b'\r\n',b'\n'))

def backend_source_files(root):
    backend = root/'backend'
    return sorted(
        path for path in backend.rglob('*.py')
        if not BACKEND_SOURCE_EXCLUSIONS.intersection(path.relative_to(backend).parts)
    )

def source_files(root):
    found = []
    for directory in ('app','components','hooks','lib'):
        found.extend(p for p in (root/directory).rglob('*') if p.is_file() and p.suffix in ('.tsx','.ts','.css'))
    found.extend(backend_source_files(root))
    for relative in ('package.json','package-lock.json','components.json','styles/globals.css','backend/config.yml','backend/requirements.txt','config/thresholds.toml','bench/calibrate.py','next.config.mjs'):
        if (root/relative).is_file():
            found.append(root/relative)
    return sorted(set(found))

def generate(root):
    css = (root/'app/globals.css').read_text(encoding='utf-8')
    block = re.search(r':root\s*\{([^}]+)\}',css)
    if not block:
        raise ValueError('Missing canonical :root token block')
    tokens = dict(re.findall(r'(--[\w-]+)\s*:\s*([^;]+);',block[1]))
    if not {'--background','--foreground','--primary','--radius'} <= tokens.keys():
        raise ValueError('Incomplete canonical design tokens')
    config = json.loads((root/'components.json').read_text(encoding='utf-8'))
    if config['tailwind']['css'] != 'app/globals.css':
        raise ValueError('Component generator points at a different design system')
    layout = (root/'app/layout.tsx').read_text(encoding='utf-8')
    if "import './globals.css'" not in layout and 'import "./globals.css"' not in layout:
        raise ValueError('App no longer imports canonical stylesheet; review the contract')
    alias = (root/'styles/globals.css').read_text(encoding='utf-8').strip()
    if alias != "@import '../app/globals.css';":
        raise ValueError('Duplicate stylesheet must remain an import-only compatibility alias')
    hashes = {p.relative_to(root).as_posix():source_digest(p) for p in source_files(root)}
    source_id = digest(json.dumps(hashes,sort_keys=True).encode())
    package = json.loads((root/'package.json').read_text(encoding='utf-8'))
    deps = {**package.get('dependencies',{}),**package.get('devDependencies',{})}
    evidence_path=root/'docs/evidence.json'
    evidence=json.loads(evidence_path.read_text(encoding='utf-8')) if evidence_path.exists() else {'runtime_report':'bench/results/baseline-all-detection/report.json'}
    report_path=(root/evidence['runtime_report']).resolve()
    if not report_path.is_relative_to(root.resolve()):
        raise ValueError('Evidence path escapes project')
    baseline = json.loads(report_path.read_text(encoding='utf-8'))
    if baseline.get('workload_valid') is not True:
        raise ValueError('Registered runtime report is rejected or inactive: workload_valid must be true')
    model_calls = baseline.get('summary', {}).get('model_call_counts', {})
    active_groups = (
        model_calls.get('violence_window', 0) > 0,
        model_calls.get('weapon_window', 0) > 0,
        model_calls.get('person_onnx', 0) > 0 or model_calls.get('person_yolo', 0) > 0,
    )
    if not all(active_groups):
        raise ValueError('Registered runtime report is inactive: violence, weapon, and person inference must all have completed calls')
    recorded = baseline['environment']['source_hashes']
    normalizations = baseline.get('source_normalizations', {})
    changed = [name.replace('\\','/') for name,value in recorded.items() if not (root/name.replace('\\','/')).is_file() or digest((root/name.replace('\\','/')).read_bytes()) not in (value, normalizations.get(name, {}).get('current_sha256') if normalizations.get(name, {}).get('original_sha256') == value else None)]
    recorded_names = {name.replace('\\','/') for name in recorded}
    unrecorded = [path.relative_to(root).as_posix() for path in backend_source_files(root)
        if path.relative_to(root).as_posix() not in recorded_names]
    manifest = {'schema_version':1,'authority':'AGENTS.md','source_fingerprint':source_id,'source_sha256':hashes,
        'baseline_revision':baseline['environment']['revision'],'baseline_backend_changed':changed,
        'baseline_backend_unrecorded':unrecorded,
        'evidence_workload_valid':True,
        'meaning':'Source consistency only; no evidence of runtime acceptance. Environment/hardware must be revalidated.'}
    manifest['evidence_report']=evidence['runtime_report']
    manifest['measured_source_normalizations']=normalizations
    manifest['evidence_sha256']=source_digest(report_path)
    if evidence_path.exists():
        manifest['evidence_registry_sha256']=source_digest(evidence_path)
    theme_block=re.search(r'@theme\s+inline\s*\{([^}]+)\}',css)
    theme=dict(re.findall(r'(--[\w-]+)\s*:\s*([^;]+);',theme_block[1])) if theme_block else {}
    token_doc = {'generated_from':'app/globals.css','source_sha256':hashes['app/globals.css'],'tokens':tokens,'theme_mapping':theme}
    design = '# Design system — current implementation\n\nGenerated by `npm run docs:sync`. Edit the source stylesheet and component implementations, never this generated file. “Current” means this checkout, not the newest upstream package release.\n\n'
    design += f'Stylesheet fingerprint: `{hashes["app/globals.css"]}`. Component preset: `{config["style"]}`. Icons: `{config.get("iconLibrary","unspecified")}`.\n\n'
    design += '## Authoritative sources\n\n- `app/globals.css`: semantic colors, theme mapping, radii, utilities and motion.\n- `app/layout.tsx`: loaded fonts, page language and global stylesheet.\n- `components/ui/`: reusable component variants and sizing.\n- `components.json`: generator configuration pointing to the same stylesheet.\n- `app/page.tsx` and imported dashboard components: implemented layout and navigation.\n\n'
    design += '## Tokens\n\n| Token | Current value |\n|---|---|\n' + ''.join(f'| `{key}` | `{value}` |\n' for key,value in tokens.items())
    design += '\n## Typography and radius mapping\n\n| Token | Source value |\n|---|---|\n'+''.join(f'| `{key}` | `{value}` |\n' for key,value in theme.items() if key.startswith(('--font-','--radius')))
    button=root/'components/ui/button.tsx'
    if button.exists():
        sizes=re.search(r'size:\s*\{(.*?)\}',button.read_text(encoding='utf-8'),re.S)
        if sizes:
            entries=re.findall(r"['\"]?([\w-]+)['\"]?\s*:\s*['\"]([^'\"]+)['\"]",sizes[1])
            design += '\n## Button sizes from components/ui/button.tsx\n\n| Variant | Implemented classes |\n|---|---|\n'+''.join(f'| `{key}` | `{value}` |\n' for key,value in entries)
    design += '\n## Rules for subsequent changes\n\nUse semantic tokens and existing component variants. Add a shared token to app/globals.css when needed; do not create a second palette or copy a theme from an old presentation. Typography must follow the actual font loading in app/layout.tsx; do not claim Arabic/RTL support without implementing and testing it. Spacing, breakpoints, focus and motion must be reviewed in their component context; this snapshot is not an accessibility certification.\n\nThe implemented telemetry lives in components/pipeline-telemetry.tsx and lib/pipeline-telemetry.ts; model series use independent completion IDs. Local Arabic factual summaries live in components/ai-report.tsx and lib/local-report.ts, with optional online reporting disclosed separately. Keep missing, loading, disconnected and failed states distinct. A live label requires a live source; file playback is labeled playback. Display a confirmed alert only from the decision contract. Unmeasured latency stays unavailable. These are required interaction rules, not claims that every current component already complies.\n\nThe current CSS contains legacy decorative utilities and components may still use local literal colors. This consolidation establishes authority; it does not certify that every screen is visually consistent. Refresh the generated reference after implementation changes and run the consistency check. The preview displays current tokens, not a replacement dashboard.\n'
    swatches=''.join(f'<article><span style="background:{html.escape(value,quote=True)}"></span><code>{html.escape(key)}</code><small>{html.escape(value)}</small></article>' for key,value in tokens.items() if re.fullmatch(r'#[0-9a-fA-F]{3,8}',value))
    preview='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AI Sentinel — current design tokens</title><style>
body{background:#0f172a;color:#e2e8f0;font:16px system-ui;margin:0;padding:32px}main{max-width:1100px;margin:auto}h1{font-size:28px}p{color:#94a3b8;line-height:1.6}section{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px}article{border:1px solid #334155;border-radius:10px;padding:14px;display:grid;gap:8px}span{height:70px;border-radius:6px}code{overflow-wrap:anywhere}small{color:#94a3b8}input{background:#1e293b;color:#e2e8f0;border:1px solid #64748b;padding:12px;margin:12px 0 24px;width:min(400px,90%)}input:focus{outline:2px solid #3b82f6} [hidden]{display:none}</style><main><h1>AI Sentinel · current design reference</h1><p>Generated from app/globals.css. This is a token reference, not evidence that the dashboard or accessibility gates passed.</p><label for="filter">Filter tokens</label><br><input id="filter" type="search" placeholder="primary, background, warning…"><section>'''+swatches+'''</section></main><script>document.getElementById('filter').addEventListener('input',e=>{for(const card of document.querySelectorAll('article'))card.hidden=!card.textContent.toLowerCase().includes(e.target.value.toLowerCase())})</script></html>'''
    palette=':root{'+''.join(f'{key}:{value};' for key,value in tokens.items() if re.fullmatch(r'#[0-9a-fA-F]{3,8}',value))+'}'
    preview=preview.replace('<style>','<style>'+palette)
    for literal,key in [('#0f172a','--background'),('#e2e8f0','--foreground'),('#94a3b8','--secondary-foreground'),('#334155','--border'),('#1e293b','--card'),('#64748b','--muted-foreground'),('#3b82f6','--primary')]:
        # Only preview layout rules, not the source-token declarations/swatches.
        begin=preview.index('body{')
        end=preview.index('</style>')
        preview=preview[:begin]+preview[begin:end].replace(literal,f'var({key})')+preview[end:]
    current = '# Current project state\n\nThis is the sole current-state entry point. Generated from this checkout and recorded evidence. No document named “final”, old version label, presentation, or archived agent prompt overrides it.\n\n'
    current += f'Implementation fingerprint: `{source_id}`. Package-declared versions: Next `{deps.get("next")}`, React `{deps.get("react")}`, Tailwind `{deps.get("tailwindcss")}`. These are declarations; package-lock.json defines the resolved installation.\n\n'
    current += '## Implemented surface\n\nNext dashboard: app/ and components/. Backend: backend/api.py and its pipeline modules. Root frontend source is authoritative; frontend/, design_extract/ and presentations are not alternate runtime authorities. The registered run identifies its actually loaded model and providers. The current pipeline has camera-scoped decisions, source timestamps, bounded model workers, model-specific observation identities, and health telemetry. The dashboard distinguishes replay/offline/stale observations and offers a local Arabic factual summary. These implemented capabilities do not certify accuracy or camera acceptance.\n\n'
    fps=(baseline.get('summary',{}).get('render_fps') or {}).get('p50')
    current += '## Latest registered evidence, not a readiness claim\n\n'
    current += f'Registered report: `{evidence["runtime_report"]}`. Workload: {evidence.get("workload","unspecified")}. Recorded render FPS median: {fps if fps is not None else "unmeasured"}. This is not live camera throughput unless the report explicitly establishes it.\n\n'
    current += evidence.get('operator_status','Camera availability unverified.')+'\n\n'
    current += evidence.get('validation_summary','Validation summary not registered.')+'\n\n'
    current += 'Read docs/ISSUES.md for unresolved defects and the gate report registered in docs/evidence.json. Changing this registry requires new evidence and review; it never triggers gate acceptance.\n\n'
    if not changed and not unrecorded:
        current += 'Recorded backend source hashes still match; hardware, environment and camera availability are not continuously monitored.\n'
    else:
        current += '**Baseline source is stale or incomplete for this checkout. Re-run relevant measurements before making current performance/correctness claims.**'
        if changed:
            current += ' Changed files: '+', '.join(f'`{p}`' for p in changed)+'.'
        if unrecorded:
            current += ' Backend source files not covered by the registered report: '+', '.join(f'`{p}`' for p in unrecorded)+'.'
        current += '\n'
    current += '\n## Work authority\n\nThe current user task controls scope. docs/PLAN.md holds pending rebuild work, not completed features. Documentation/design consolidation is authorized independently of blocked live measurements. Do not reopen settled historical debates or import old freezes, agent approval loops or obsolete model claims. Verify a disputed current fact against code and evidence and correct the one canonical document.\n\n## Refresh\n\nRun `npm run docs:sync` after source changes, then `npm run docs:check`. Generated fields follow implementation; measured claims require new evidence and must never be upgraded just by refreshing documentation. See docs/MAINTENANCE.md.\n'
    blueprint = load_blueprint(root)
    counts = {}
    for entry in blueprint['entries']:
        counts[entry['kind']] = counts.get(entry['kind'], 0) + 1
    current += '\n## Living blueprint (generated pointer)\n\nThe scoped, non-authoritative living blueprint extends this status document: `docs/blueprint/INDEX.md` (generated) from `docs/blueprint/index.json` (validated input). ID namespaces: `F-01`…`F-49` runtime features, `U-01`…`U-10` UI screens, `SC-1`…`SC-10` shared contracts, `S-01`…`S-22` ownership slices, `B-1`…`B-10` baseline integrity findings, `N-1`…`N-16` negative findings, `R-1`…`R-8` risks. Registered entries: ' + ', '.join(f'{kind} {count}' for kind, count in sorted(counts.items())) + '. `npm run docs:check` fails when the index disagrees with recorded source fingerprints or when a canonical document cites an unknown blueprint id; stale entries must be re-assessed in `docs/blueprint/index.json`, never silenced. The blueprint is not a status or design authority.\n'
    outputs = dict(zip(OUTPUTS,(json.dumps(manifest,indent=2)+'\n',json.dumps(token_doc,indent=2)+'\n',design,preview,current)))
    outputs[BLUEPRINT_VIEW] = blueprint_view(root)
    return outputs

def strip_ref(ref):
    return re.sub(r':\d[\d,\s-]*$', '', str(ref)).replace('\\', '/')

def path_like(ref):
    value = strip_ref(ref)
    if '*' in value or value.startswith('/') or '/' not in value:
        return False
    last = value.rstrip('/').rsplit('/', 1)[-1]
    return re.fullmatch(r'[A-Za-z0-9_.\-/]+', value) is not None and (value.endswith('/') or '.' in last)

def known_basenames(root):
    names = {p.name for p in root.iterdir() if p.is_file()}
    for directory in ('backend', 'tests', 'bench', 'components', 'hooks', 'lib', 'app', 'scripts'):
        for path in (root / directory).rglob('*'):
            if path.is_file():
                names.add(path.name)
    return names

def load_blueprint(root):
    path = root / BLUEPRINT_INDEX
    if not path.is_file():
        raise ValueError('Missing blueprint index: ' + BLUEPRINT_INDEX)
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        raise ValueError('Blueprint index is not valid JSON: ' + str(exc))
    if data.get('schema_version') != 1 or data.get('kind') != 'living-blueprint-index':
        raise ValueError('Blueprint index has an unknown schema')
    if data.get('non_authoritative') is not True:
        raise ValueError('Blueprint index must declare non_authoritative: true')
    entries = data.get('entries')
    if not isinstance(entries, list) or not entries:
        raise ValueError('Blueprint index entries must be a non-empty list')
    seen = set()
    for entry in entries:
        for field in ENTRY_FIELDS:
            if field not in entry:
                raise ValueError('Blueprint entry missing field ' + field + ': ' + repr(entry.get('id')))
        identifier = entry['id']
        pattern = KIND_ID.get(entry['kind'])
        if pattern is None or not pattern.fullmatch(identifier):
            raise ValueError('Blueprint entry has id/kind mismatch: ' + identifier)
        if identifier in seen:
            raise ValueError('Duplicate blueprint entry id: ' + identifier)
        seen.add(identifier)
        if entry['status'] not in STATUSES:
            raise ValueError('Blueprint entry has unknown status: ' + identifier)
        for field in ('source_refs', 'tests', 'evidence', 'limitations'):
            if not isinstance(entry[field], list):
                raise ValueError('Blueprint entry field ' + field + ' must be a list: ' + identifier)
        if not isinstance(entry.get('known_absent', []), list):
            raise ValueError('Blueprint entry field known_absent must be a list: ' + identifier)
    return data

def blueprint_failures(root):
    # Referential and fingerprint agreement between the blueprint index and
    # this checkout. Red here can only be fixed by re-assessing the index,
    # never by deleting this check.
    data = load_blueprint(root)
    entries = data['entries']
    ids = {entry['id'] for entry in entries}
    failures = []
    names = known_basenames(root)
    for item in data.get('inputs', ()):
        path = root / item.get('path', '')
        if not path.is_file():
            failures.append('Blueprint input missing: ' + str(item.get('path')))
        elif item.get('sha256') != source_digest(path):
            failures.append('Blueprint input fingerprint mismatch: ' + item['path'] + ' — re-assess docs/blueprint/index.json')
    for entry in entries:
        identifier = entry['id']
        absent = set(entry.get('known_absent', ()))
        for ref in entry['source_refs'] + entry['tests']:
            value = strip_ref(ref)
            if '*' in value or value in absent:
                continue
            if path_like(ref):
                target = root / value
                if not (target.is_dir() if value.endswith('/') else target.is_file()):
                    failures.append('Blueprint entry ' + identifier + ' references missing source: ' + value)
            elif '/' not in value and value not in names:
                failures.append('Blueprint entry ' + identifier + ' references missing test: ' + value)
        for ev in entry['evidence']:
            target, _, anchor = str(ev).partition('#')
            path = root / target
            if not path.is_file():
                failures.append('Blueprint entry ' + identifier + ' references missing evidence document: ' + target)
            elif anchor and not re.search(r'^#{2,3}\s+' + re.escape(anchor) + r'\b', path.read_text(encoding='utf-8'), re.M):
                failures.append('Blueprint entry ' + identifier + ' references stale evidence anchor: ' + ev)
        for values in (entry.get('links') or {}).values():
            for target in values:
                if target not in ids:
                    failures.append('Blueprint entry ' + identifier + ' links unknown blueprint id: ' + str(target))
        for name, recorded in (entry.get('assessed') or {}).items():
            path = root / name
            if not path.is_file():
                failures.append('Blueprint entry ' + identifier + ' has a stale source fingerprint for missing file: ' + name)
            elif recorded != source_digest(path):
                failures.append('Blueprint entry ' + identifier + ' disagrees with source fingerprint for ' + name + '; re-assess the entry before updating docs/blueprint/index.json')
    for relative in SCAN_DOCS:
        path = root / relative
        if not path.is_file():
            continue
        for token in ID_SCAN.findall(path.read_text(encoding='utf-8')):
            if token not in ids:
                failures.append('Canonical document ' + relative + ' cites unknown blueprint id: ' + token)
    return failures

def blueprint_view(root):
    data = load_blueprint(root)
    entries = data['entries']
    stale = {}
    for entry in entries:
        for name, recorded in (entry.get('assessed') or {}).items():
            path = root / name
            if not path.is_file() or recorded != source_digest(path):
                stale.setdefault(entry['id'], []).append(name)
    out = ['---', 'authority: scoped', 'non_authoritative: true', '---', '',
           '# AI Sentinel — living blueprint (generated view)', '',
           'Generated by `npm run docs:sync` from `docs/blueprint/index.json` (validated input) and current source fingerprints. Never hand-edit. ' + data.get('authority_note', ''), '',
           '## Inputs and fingerprints', '', '| Input | Produced by | Recorded fingerprint | State |', '|---|---|---|---|']
    for item in data.get('inputs', ()):
        path = root / item['path']
        current = source_digest(path) if path.is_file() else 'missing'
        state = 'ok' if current == item.get('sha256') else '**CHANGED — re-assess**'
        out.append(f"| `{item['path']}` | {item['produced_by']} | `{str(item.get('sha256'))[:16]}` | {state} |")
    out += ['', '## ID namespaces', '', '| Namespace | Meaning |', '|---|---|']
    for key, value in (data.get('id_namespaces') or {}).items():
        out.append(f'| `{key}` | {value} |')
    counts = {}
    for entry in entries:
        counts[(entry['kind'], entry['status'])] = counts.get((entry['kind'], entry['status']), 0) + 1
    out += ['', '## Status summary', '', '| Kind | ' + ' | '.join(STATUSES) + ' |', '|---' * (len(STATUSES) + 1) + '|']
    for kind in ('runtime', 'ui', 'contract', 'slice', 'finding'):
        out.append('| ' + kind + ' | ' + ' | '.join(str(counts.get((kind, status), 0)) for status in STATUSES) + ' |')
    out += ['', '## Status semantics', '']
    for key, value in (data.get('status_semantics') or {}).items():
        out.append(f'- `{key}`: {value}')
    if data.get('known_limitations'):
        out += ['', '## Known limitations', '']
        for note in data['known_limitations']:
            out.append('- ' + note)

    def fp(entry):
        touched = stale.get(entry['id'])
        return 'ok' if not touched else '**STALE**: ' + ', '.join(f'`{p}`' for p in touched)

    def one(text, limit=160):
        text = str(text)
        return text if len(text) <= limit else text[:limit].rsplit(' ', 1)[0] + ' …'

    groups = [('UI screens (U)', 'ui'), ('Runtime features (F)', 'runtime'),
              ('Shared contracts (SC)', 'contract'), ('Ownership slices (S)', 'slice'),
              ('Findings and risks (B/N/R)', 'finding')]
    for heading, kind in groups:
        out += ['', f'## {heading}', '']
        if kind == 'ui':
            out += ['| ID | Title | Status | Consumes | Contracts | Limitations | Fingerprint |', '|---|---|---|---|---|---|---|']
        elif kind == 'runtime':
            out += ['| ID | Title | Status | Primary source | Tests | Links | Fingerprint |', '|---|---|---|---|---|---|---|']
        elif kind == 'contract':
            out += ['| ID | Title | Status | Source refs | Limitations | Fingerprint |', '|---|---|---|---|---|---|']
        elif kind == 'slice':
            out += ['| ID | Title | Status | Owns | Features | Fingerprint |', '|---|---|---|---|---|---|']
        else:
            out += ['| ID | Category | Status | Title | Evidence | Fingerprint |', '|---|---|---|---|---|---|']
        for entry in entries:
            if entry['kind'] != kind:
                continue
            links = entry.get('links') or {}
            if kind == 'ui':
                out.append(f"| [{entry['id']}](#{entry['id'].lower()}) | {entry['title']} | {entry['status']} | "
                           f"{', '.join(links.get('features', [])) or '—'} | {', '.join(links.get('contracts', [])) or '—'} | "
                           f"{one(entry['limitations'][0] if entry['limitations'] else '—')} | {fp(entry)} |")
            elif kind == 'runtime':
                links_all = sorted(set(sum(links.values(), [])))
                out.append(f"| [{entry['id']}](#{entry['id'].lower()}) | {entry['title']} | {entry['status']} | "
                           f"`{strip_ref(entry['source_refs'][0]) if entry['source_refs'] else '—'}` | "
                           f"{len(entry['tests'])} file(s) | {', '.join(links_all) or '—'} | {fp(entry)} |")
            elif kind == 'contract':
                out.append(f"| [{entry['id']}](#{entry['id'].lower()}) | {entry['title']} | {entry['status']} | "
                           f"{', '.join('`'+strip_ref(r)+'`' for r in entry['source_refs'][:3]) or '—'} | "
                           f"{one(entry['limitations'][0] if entry['limitations'] else '—')} | {fp(entry)} |")
            elif kind == 'slice':
                out.append(f"| [{entry['id']}](#{entry['id'].lower()}) | {entry['title']} | {entry['status']} | "
                           f"{', '.join('`'+strip_ref(r)+'`' for r in entry['source_refs'][:4]) or '—'} | "
                           f"{', '.join(links.get('features', [])) or '—'} | {fp(entry)} |")
            else:
                out.append(f"| [{entry['id']}](#{entry['id'].lower()}) | {entry.get('category', '—')} | {entry['status']} | "
                           f"{entry['title']} | {', '.join(entry['evidence']) or '—'} | {fp(entry)} |")
    out += ['', '## Entry details', '']
    for entry in entries:
        out += [f"### {entry['id']}", '', f"{entry['title']} — kind `{entry['kind']}`, status `{entry['status']}`.", '']
        if entry['source_refs']:
            out.append('Source refs: ' + ', '.join(f'`{r}`' for r in entry['source_refs']))
        if entry['tests']:
            out.append('Tests: ' + ', '.join(f'`{r}`' for r in entry['tests']))
        if entry['evidence']:
            out.append('Evidence: ' + ', '.join(f'`{r}`' for r in entry['evidence']))
        if entry.get('contract'):
            out.append('Contract: ' + entry['contract'])
        links = entry.get('links') or {}
        if any(links.values()):
            out.append('Links: ' + '; '.join(f'{k}=' + ', '.join(v) for k, v in sorted(links.items()) if v))
        assessed = entry.get('assessed') or {}
        if assessed:
            out.append('Source fingerprints: ' + '; '.join(f'`{k}` → `{v[:16]}`' + ('' if not stale.get(entry['id']) or k not in stale[entry['id']] else ' (**STALE**)') for k, v in sorted(assessed.items())))
        for limitation in entry['limitations']:
            out.append('- Limitation: ' + limitation)
        out.append('')
    out += ['## Stale source fingerprints', '']
    if stale:
        for identifier, names_ in sorted(stale.items()):
            out.append(f"- `{identifier}`: " + ', '.join(f'`{n}`' for n in names_))
        out += ['', 'Re-assess each entry against the changed source and update `docs/blueprint/index.json`; never silence this list.']
    else:
        out.append('None: every recorded source fingerprint matches this checkout.')
    out.append('')
    return '\n'.join(out)

def check_policy(root):
    policy=json.loads((root/'docs/authority.json').read_text(encoding='utf-8'))
    failures=[]
    allowed=set(policy['canonical_docs'])
    for relative in sorted(allowed):
        path=root/relative
        if not path.is_file():
            continue
        try:
            text=path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            failures.append('Canonical document is not valid UTF-8: '+relative)
            continue
        if any(marker in text for marker in MOJIBAKE_MARKERS):
            failures.append('Canonical document contains mojibake: '+relative)
    scoped=policy.get('scoped_artifacts',{})
    scoped_roots=tuple(scoped.get('roots',()))
    markers=scoped.get('marker',{}).get('required',{})
    registries=set()
    for relative in scoped.get('alternate_registries',()):
        path=root/relative
        if not path.is_file():
            continue
        try:
            registries.update(str(item.get('path','')) for item in json.loads(path.read_text(encoding='utf-8')).get('documents',()))
        except json.JSONDecodeError:
            failures.append('Scoped artifact registry is not valid JSON: '+relative)
    def scoped_marked(path):
        parts=path.read_text(encoding='utf-8').split('---',2)
        if len(parts)<3:
            return False
        front=parts[1]
        return all(re.search(r'^'+re.escape(key)+r':\s*'+re.escape(str(value).lower())+r'\s*$',front,re.M) for key,value in markers.items())
    for path in (root/'docs').rglob('*.md'):
        relative=path.relative_to(root).as_posix()
        if relative in allowed:
            if scoped_roots and relative.startswith(scoped_roots):
                failures.append('Scoped artifact promoted to canonical document: '+relative)
            continue
        if scoped_roots and relative.startswith(scoped_roots):
            if not scoped_marked(path) and relative not in registries:
                failures.append('Scoped document missing non-authority marker: '+relative)
            continue
        failures.append('Unregistered active document: '+relative)
    for relative in policy['retired_paths']:
        if (root/relative).is_file():
            failures.append('Retired document/prompt returned: '+relative)
    for relative in policy['agent_entrypoints']:
        path=root/relative
        reference='docs/CURRENT.md' if relative=='AGENTS.md' else 'AGENTS.md'
        if not path.is_file() or reference not in path.read_text(encoding='utf-8'):
            failures.append('Agent entrypoint lost canonical reference: '+relative)
    kilo=root/'.kilo/kilo.jsonc'
    if kilo.exists():
        settings=json.loads(kilo.read_text(encoding='utf-8'))
        for name,definition in settings.get('agent',{}).items():
            if isinstance(definition,dict) and 'AGENTS.md' not in definition.get('prompt',''):
                failures.append('Agent prompt lost canonical reference: '+name)
    return failures

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--write',action='store_true')
    parser.add_argument('--check',action='store_true')
    parser.add_argument('--check-design',action='store_true',help='Portable authority/design check; does not certify the local runtime-source snapshot')
    parser.add_argument('--check-blueprint',action='store_true',help='Scoped check: authority policy plus the living blueprint index and view')
    args=parser.parse_args()
    outputs=generate(ROOT)
    failures=check_policy(ROOT)
    if not args.check_design:
        failures+=blueprint_failures(ROOT)
    for relative,text in outputs.items():
        if args.check_design and relative not in ('docs/DESIGN.md','docs/design-tokens.json','docs/design-preview.html'):
            continue
        if args.check_blueprint and relative!=BLUEPRINT_VIEW:
            continue
        path=ROOT/relative
        if args.write:
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(text,encoding='utf-8',newline='\n')
        elif not path.is_file() or path.read_text(encoding='utf-8')!=text:
            failures.append('Stale generated document: '+relative)
    if failures:
        print('\n'.join(failures))
        return 1
    mode='portable design snapshots' if args.check_design else 'blueprint view' if args.check_blueprint else 'local design/source snapshots'
    print('Documentation authority and '+mode+' are consistent. Runtime gates are not certified.')
    return 0

if __name__=='__main__':
    raise SystemExit(main())

import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import YAML from 'yaml'
import { api, ApiError } from '../api/client'
import type { ConceptDetail, TreeNode } from '../api/types'
import ConceptGraph from '../components/ConceptGraph'
import { Empty, ErrorBox, Loading, Markdown, StatusBadge, TrustBadge, useIdentity } from '../components/common'

function Tree({ node, onOpen, current, depth = 0 }: { node: TreeNode; onOpen: (id: string) => void; current?: string; depth?: number }) {
  const [open, setOpen] = useState(depth < 1 || (!!current && current.startsWith(node.path + '/')))
  return (
    <div className="tree-node">
      {depth > 0 && (
        <button className="tree-dir" onClick={() => setOpen(!open)} aria-expanded={open}>
          {open ? '▾' : '▸'} {node.name} <span className="fine">{node.count}</span>
        </button>
      )}
      {open && (
        <div className={depth > 0 ? 'tree-children' : ''}>
          {node.dirs.map((d) => <Tree key={d.path} node={d} onOpen={onOpen} current={current} depth={depth + 1} />)}
          {node.concepts.map((c) => (
            <button key={c.id} className={`tree-leaf ${c.id === current ? 'active' : ''}`} onClick={() => onOpen(c.id)} title={c.type}>
              {c.title}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function Editor({ bundle, concept, isNew, onDone }: { bundle: string; concept?: ConceptDetail; isNew: boolean; onDone: (id: string) => void }) {
  const { actor } = useIdentity()
  const qc = useQueryClient()
  const strip = (fm: Record<string, unknown>) => {
    const { generated: _g, verified: _v, ...rest } = fm // eslint-disable-line @typescript-eslint/no-unused-vars
    return rest
  }
  const [id, setId] = useState(concept?.id ?? '')
  const [fm, setFm] = useState(YAML.stringify(concept ? strip(concept.frontmatter) : { type: 'Note', title: '', description: '', tags: [] }))
  const [body, setBody] = useState(concept?.body ?? '')
  const [summary, setSummary] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const save = useMutation({
    mutationFn: () => {
      let parsed: unknown
      try {
        parsed = YAML.parse(fm)
      } catch (e) {
        throw new Error(`Frontmatter is not valid YAML: ${(e as Error).message}`)
      }
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('Frontmatter must be a YAML mapping')
      if (!(parsed as Record<string, unknown>).type) throw new Error('`type` is required (OKF §4.1)')
      return api.saveConcept(bundle, id, { frontmatter: parsed as Record<string, unknown>, body, base_hash: isNew ? null : concept!.content_hash, actor: actor!, summary })
    },
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['okf', bundle] })
      if (r.sync_failures?.length) alert(`Saved, but index sync failed: ${r.sync_failures.map((f) => f.error).join('; ')}`)
      onDone(r.concept_id)
    },
    onError: (e) => setErr(e instanceof ApiError && e.status === 409 ? `${e.message}. Your text is kept below; reload the concept and re-apply.` : (e as Error).message),
  })
  if (!actor) return <div className="state error">Set your reviewer id (top right) before editing: edits are recorded as `human:&lt;id&gt;`.</div>
  return (
    <form className="editor" onSubmit={(e) => { e.preventDefault(); setErr(null); save.mutate() }}>
      {isNew && (
        <label>Concept id (path without .md)
          <input value={id} onChange={(e) => setId(e.target.value)} placeholder="guides/deployment" required pattern="[A-Za-z0-9_][A-Za-z0-9_.\-/]*" />
        </label>
      )}
      <label>Frontmatter (YAML; `generated` and `verified` are set for you)
        <textarea className="mono" rows={8} value={fm} onChange={(e) => setFm(e.target.value)} />
      </label>
      <label>Body (Markdown; link concepts as <code>[text](/folder/concept.md)</code>)
        <textarea className="mono" rows={16} value={body} onChange={(e) => setBody(e.target.value)} />
      </label>
      <label>Change summary <input value={summary} onChange={(e) => setSummary(e.target.value)} maxLength={500} /></label>
      {err && <div className="state error">{err}</div>}
      <div className="row">
        <button className="primary" type="submit" disabled={save.isPending}>{save.isPending ? 'Saving…' : `Save as ${actor}`}</button>
        <button type="button" onClick={() => onDone(concept?.id ?? '')}>Cancel</button>
      </div>
    </form>
  )
}

function ConceptView({ bundle, id, onOpen }: { bundle: string; id: string; onOpen: (id: string) => void }) {
  const [editing, setEditing] = useState(false)
  const [tab, setTab] = useState<'doc' | 'graph' | 'history'>('doc')
  const q = useQuery({ queryKey: ['okf', bundle, 'concept', id], queryFn: () => api.concept(bundle, id) })
  const graph = useQuery({ queryKey: ['okf', bundle, 'graph', id], queryFn: () => api.graph(bundle, id, 2), enabled: tab === 'graph' })
  useEffect(() => { setEditing(false) }, [id])
  if (q.isLoading) return <Loading />
  if (q.isError) return <ErrorBox error={q.error} />
  const c = q.data!
  if (editing) return <Editor bundle={bundle} concept={c} isNew={false} onDone={() => setEditing(false)} />
  const known = new Set(['type', 'title', 'description', 'tags', 'resource', 'generated', 'verified', 'status', 'stale_after', 'sources'])
  return (
    <article className="concept">
      <header>
        <div className="fine"><code>{c.id}</code> · {c.type}</div>
        <h2>{c.title}</h2>
        {c.description && <p className="lead">{c.description}</p>}
        <div className="row">
          <TrustBadge tier={c.trust_tier} /> <StatusBadge status={c.status} stale={c.stale} />
          {c.tags.map((t) => <span key={t} className="badge tag">#{t}</span>)}
          {c.pending_proposals.length > 0 && <Link className="badge status-draft" to={`/review/${c.pending_proposals[0]}`}>{c.pending_proposals.length} pending proposal(s)</Link>}
          <span className="spacer" />
          <button onClick={() => setEditing(true)}>Edit</button>
        </div>
      </header>
      <nav className="tabs">
        {(['doc', 'graph', 'history'] as const).map((t) => <button key={t} className={tab === t ? 'active' : ''} onClick={() => setTab(t)}>{t === 'doc' ? 'Document' : t === 'graph' ? 'Links graph' : 'History'}</button>)}
      </nav>
      {tab === 'doc' && (
        <div className="concept-grid">
          <Markdown text={c.body} conceptId={c.id} onConcept={onOpen} />
          <aside className="meta">
            <h4>Metadata</h4>
            <dl>
              {c.frontmatter.resource ? <><dt>Resource</dt><dd><a href={String(c.frontmatter.resource)} target="_blank" rel="noreferrer">{String(c.frontmatter.resource)}</a></dd></> : null}
              <dt>Generated</dt><dd>{c.generated_by ?? '—'}<br /><span className="fine">{c.generated_at}</span></dd>
              <dt>Verified</dt><dd>{JSON.stringify(c.frontmatter.verified ?? 'never')}</dd>
              {c.frontmatter.stale_after ? <><dt>Stale after</dt><dd>{String(c.frontmatter.stale_after)}</dd></> : null}
              {Object.entries(c.frontmatter).filter(([k]) => !known.has(k)).map(([k, v]) => <div key={k}><dt>{k}</dt><dd className="mono small">{typeof v === 'object' ? JSON.stringify(v) : String(v)}</dd></div>)}
            </dl>
            {c.sources.length > 0 && <><h4>Sources</h4><ul className="plain">{c.sources.map((s, i) => <li key={i}>{s.id && <code>{s.id}</code>} <a href={s.resource} target="_blank" rel="noreferrer">{s.title ?? s.resource}</a></li>)}</ul></>}
            <h4>Links ({c.links.filter((l) => !l.external).length})</h4>
            <ul className="plain">
              {c.links.filter((l) => !l.external).map((l, i) => (
                <li key={i}>{l.broken ? <span className="broken" title="target not in bundle (allowed by OKF §6.1)">{l.text} → {l.target}</span> : <a href="#" onClick={(e) => { e.preventDefault(); onOpen(l.resolved!.replace(/\/$/, '')) }}>{l.text}</a>}</li>
              ))}
            </ul>
            <h4>Backlinks ({c.backlinks.length})</h4>
            <ul className="plain">{c.backlinks.map((b) => <li key={b.id}><a href="#" onClick={(e) => { e.preventDefault(); onOpen(b.id) }}>{b.title}</a></li>)}</ul>
            {(c.warnings.length > 0 || c.errors.length > 0) && <><h4>Conformance</h4>{[...c.errors, ...c.warnings].map((w) => <div key={w} className="fine">⚠ {w}</div>)}</>}
          </aside>
        </div>
      )}
      {tab === 'graph' && (graph.isLoading ? <Loading /> : graph.isError ? <ErrorBox error={graph.error} /> :
        <ConceptGraph nodes={graph.data!.nodes} edges={graph.data!.edges} center={c.id} onSelect={onOpen} />)}
      {tab === 'history' && (
        c.history.length === 0 ? <Empty>No EIH-recorded changes. (Changes made outside EIH show in git history.)</Empty> :
        <table className="data"><thead><tr><th>When</th><th>Action</th><th>Actor</th><th>Details</th></tr></thead><tbody>
          {c.history.map((h, i) => <tr key={i}><td>{new Date(h.at).toLocaleString()}</td><td>{h.action}</td><td><code>{h.actor}</code></td><td className="small">{String(h.summary ?? h.note ?? h.proposal_id ?? '')}</td></tr>)}
        </tbody></table>
      )}
    </article>
  )
}

export default function KnowledgePage() {
  const [params, setParams] = useSearchParams()
  const qc = useQueryClient()
  const bundles = useQuery({ queryKey: ['okf', 'bundles'], queryFn: api.bundles })
  const bundle = params.get('bundle') ?? bundles.data?.find((b) => b.default)?.name ?? bundles.data?.[0]?.name
  const concept = params.get('concept') ?? undefined
  const [query, setQuery] = useState('')
  const [mode, setMode] = useState<'lexical' | 'semantic'>('lexical')
  const [view, setView] = useState<'concept' | 'new' | 'overview'>('concept')
  const tree = useQuery({ queryKey: ['okf', bundle, 'tree'], queryFn: () => api.tree(bundle!), enabled: !!bundle })
  const search = useQuery({
    queryKey: ['okf', bundle, 'search', mode, query],
    queryFn: async () => (mode === 'lexical' ? (await api.search(bundle!, query)).results : (await api.semantic(bundle!, query)).results),
    enabled: !!bundle && query.trim().length >= 2,
  })
  const conformance = useQuery({ queryKey: ['okf', bundle, 'conformance'], queryFn: () => api.conformance(bundle!), enabled: !!bundle && view === 'overview' })
  const log = useQuery({ queryKey: ['okf', bundle, 'log'], queryFn: () => api.log(bundle!), enabled: !!bundle && view === 'overview' })
  const overviewGraph = useQuery({ queryKey: ['okf', bundle, 'graph', '*'], queryFn: () => api.graph(bundle!), enabled: !!bundle && view === 'overview' })
  const sync = useMutation({ mutationFn: () => api.sync(bundle!), onSuccess: () => qc.invalidateQueries({ queryKey: ['okf'] }) })
  const [importErr, setImportErr] = useState<string | null>(null)

  const open = (id: string) => { setView('concept'); setParams((p) => { p.set('concept', id); if (bundle) p.set('bundle', bundle); return p }) }

  async function doImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    const name = prompt('Name for the imported bundle', file.name.replace(/\.(okf\.)?zip$/i, '').replace(/[^A-Za-z0-9_.-]/g, '-'))
    if (!name) return
    setImportErr(null)
    try {
      const r = await api.importBundle(name, file)
      await qc.invalidateQueries({ queryKey: ['okf', 'bundles'] })
      setParams({ bundle: r.imported_as })
      setView('overview')
    } catch (err) {
      setImportErr((err as Error).message)
    }
    e.target.value = ''
  }

  if (bundles.isLoading) return <Loading what="Loading bundles" />
  if (bundles.isError) return <ErrorBox error={bundles.error} />
  if (!bundle) return <Empty>No OKF bundles yet. Produce one with <code>python -m scripts.okf_produce produce</code> or import a zip.</Empty>
  const b = bundles.data!.find((x) => x.name === bundle)

  return (
    <div className="kb-layout">
      <aside className="sidebar">
        <label>Bundle
          <select value={bundle} onChange={(e) => setParams({ bundle: e.target.value })}>
            {bundles.data!.map((x) => <option key={x.name} value={x.name}>{x.name} ({x.concepts})</option>)}
          </select>
        </label>
        <div className="row small">
          <button onClick={() => setView('overview')}>Overview</button>
          <button onClick={() => setView('new')}>New concept</button>
        </div>
        <input type="search" placeholder="Search concepts…" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search concepts" />
        <div className="row small">
          <label><input type="radio" checked={mode === 'lexical'} onChange={() => setMode('lexical')} /> text</label>
          <label><input type="radio" checked={mode === 'semantic'} onChange={() => setMode('semantic')} /> semantic</label>
        </div>
        {query.trim().length >= 2 ? (
          search.isLoading ? <Loading /> : search.isError ? <ErrorBox error={search.error} /> :
          search.data!.length === 0 ? <Empty>No matches.</Empty> :
          <ul className="plain results">{search.data!.map((r) => <li key={r.id}><button className="tree-leaf" onClick={() => open(r.id)}>{r.title}</button><div className="fine">{r.type}{'score' in r && r.score !== undefined ? ` · ${r.score}` : ''}</div></li>)}</ul>
        ) : tree.isLoading ? <Loading /> : tree.isError ? <ErrorBox error={tree.error} /> : <Tree node={tree.data!} onOpen={open} current={concept} />}
      </aside>
      <section className="kb-main">
        {view === 'new' && <Editor bundle={bundle} isNew onDone={(id) => (id ? open(id) : setView('concept'))} />}
        {view === 'concept' && (concept ? <ConceptView bundle={bundle} id={concept} onOpen={open} /> : <Empty>Pick a concept from the tree, search, or open the overview.</Empty>)}
        {view === 'overview' && b && (
          <div className="overview">
            <h2>{b.name}</h2>
            <div className="row">
              <span className={`badge ${b.conformant ? 'trust-human-reviewed' : 'status-deprecated'}`}>{b.conformant ? 'OKF conformant' : `${b.errors} conformance errors`}</span>
              <span className="badge">{b.concepts} concepts</span>
              <span className="badge">{b.broken_links} unresolved links</span>
              {b.declared_okf_version && <span className="badge">okf_version {b.declared_okf_version}</span>}
              <span className="spacer" />
              <a className="button" href={api.exportUrl(b.name)}>Export zip</a>
              <label className="button">Import zip<input type="file" accept=".zip" hidden onChange={doImport} /></label>
              <button onClick={() => sync.mutate()} disabled={sync.isPending}>{sync.isPending ? 'Syncing…' : 'Re-index (Qdrant + Neo4j)'}</button>
            </div>
            {importErr && <div className="state error">{importErr}</div>}
            {sync.isError && <ErrorBox error={sync.error} />}
            {sync.data && <pre className="small">{JSON.stringify(sync.data)}</pre>}
            <h3>Types</h3>
            <div className="row">{Object.entries(b.types).map(([t, n]) => <span key={t} className="badge">{t}: {n}</span>)}</div>
            <h3>Most-linked concepts</h3>
            {overviewGraph.isLoading ? <Loading /> : overviewGraph.data && <ConceptGraph nodes={overviewGraph.data.nodes} edges={overviewGraph.data.edges} onSelect={open} />}
            <h3>Conformance report</h3>
            {conformance.data && <details><summary>{(conformance.data.errors as unknown[]).length} errors, {(conformance.data.warnings as unknown[]).length} warnings, {(conformance.data.broken_links as unknown[]).length} unresolved links</summary><pre className="small">{JSON.stringify(conformance.data, null, 2)}</pre></details>}
            <h3>log.md</h3>
            {log.data?.log ? <Markdown text={log.data.log} /> : <Empty>No log.md in this bundle.</Empty>}
          </div>
        )}
      </section>
    </div>
  )
}

// EIH tree-sitter parse service (WebAssembly; no native code, so Windows Smart App Control
// does not block it). Protocol: one JSON request per stdin line
//   {"id": 1, "lang": "java", "source": "..."}
// and one JSON response per stdout line
//   {"id": 1, "ok": true, "has_error": false, "nodes": [Node...]}
// Node = {type, start_row, end_row, name, members: [Node...]} for the root's named children.
// Rows are 0-based. Members are the named children of a container's body (class/impl/...).
import { createInterface } from 'node:readline'
import { createRequire } from 'node:module'
import { Language, Parser } from 'web-tree-sitter'

const require = createRequire(import.meta.url)
const WASM = {
  java: 'tree-sitter-java/tree-sitter-java.wasm',
  go: 'tree-sitter-go/tree-sitter-go.wasm',
  rust: 'tree-sitter-rust/tree-sitter-rust.wasm',
  javascript: 'tree-sitter-javascript/tree-sitter-javascript.wasm',
  typescript: 'tree-sitter-typescript/tree-sitter-typescript.wasm',
  tsx: 'tree-sitter-typescript/tree-sitter-tsx.wasm',
  c: 'tree-sitter-c/tree-sitter-c.wasm',
  cpp: 'tree-sitter-cpp/tree-sitter-cpp.wasm',
}
// Body field of container nodes whose members can become their own chunks.
const BODY_FIELDS = ['body', 'declaration_list', 'class_body']

await Parser.init()
const parsers = {}
async function parserFor(lang) {
  if (!WASM[lang]) throw new Error(`unsupported language ${lang}`)
  if (!parsers[lang]) {
    const p = new Parser()
    p.setLanguage(await Language.load(require.resolve(WASM[lang])))
    parsers[lang] = p
  }
  return parsers[lang]
}

const IDENT = new Set(['identifier', 'field_identifier', 'type_identifier', 'qualified_identifier',
  'destructor_name', 'operator_name', 'property_identifier', 'scoped_identifier', 'scoped_type_identifier'])

function nameOf(node) {
  if (IDENT.has(node.type)) return node.text
  const n = node.childForFieldName('name')
  if (n) return n.text
  if (node.type === 'impl_item') {  // impl Trait for Type -> "Trait for Type"; impl Type -> "Type"
    const t = node.childForFieldName('type'), tr = node.childForFieldName('trait')
    return t ? (tr ? `${tr.text} for ${t.text}` : t.text) : null
  }
  const decl = node.childForFieldName('declaration') ?? node.childForFieldName('declarator')
  if (decl) return nameOf(decl)
  if (node.type === 'template_declaration' && node.namedChildCount) return nameOf(node.namedChildren[node.namedChildCount - 1])
  for (const c of node.namedChildren) {
    if (c.type.endsWith('declarator') || c.type === 'variable_declarator' || c.type === 'type_spec') {
      const v = nameOf(c)
      if (v) return v
    }
  }
  return null
}

const FN_VALUES = new Set(['function_expression', 'function', 'arrow_function', 'generator_function', 'class'])

// CommonJS/ES5 definitions: `res.send = function send() {}`, `var f = function () {}`.
function assignedFunction(node) {
  if (node.type === 'expression_statement') {
    const e = node.namedChildren[0]
    if (e && e.type === 'assignment_expression' && FN_VALUES.has(e.childForFieldName('right')?.type)) return e.childForFieldName('left').text
  }
  if (node.type === 'variable_declaration' || node.type === 'lexical_declaration') {
    const d = node.namedChildren.find((c) => c.type === 'variable_declarator')
    if (d && FN_VALUES.has(d.childForFieldName('value')?.type)) return d.childForFieldName('name')?.text ?? null
  }
  return null
}

function describe(node, depth) {
  const assigned = assignedFunction(node)
  const out = { type: assigned ? 'assigned_function' : node.type, start_row: node.startPosition.row, end_row: node.endPosition.row,
    name: assigned ?? nameOf(node), members: [] }
  if (depth > 0) {
    let body = null
    for (const f of BODY_FIELDS) body = body ?? node.childForFieldName(f)
    const decl = node.childForFieldName('declaration')
    if (!body && decl) for (const f of BODY_FIELDS) body = body ?? decl.childForFieldName(f)
    if (body) out.members = body.namedChildren.map((c) => describe(c, 0))
  }
  return out
}

// C/C++ wrap definitions in #if/#ifdef blocks (include guards wrap whole headers): look
// inside them. The directive lines themselves are not returned, so they become code gaps.
const PREPROC = new Set(['preproc_if', 'preproc_ifdef', 'preproc_else', 'preproc_elif', 'preproc_elifdef'])
function topLevel(root) {
  const out = []
  const walk = (nodes) => {
    for (const c of nodes) {
      if (PREPROC.has(c.type)) {
        const cond = c.childForFieldName('condition') ?? c.childForFieldName('name')
        walk(c.namedChildren.filter((x) => x !== cond && x.id !== cond?.id))
      } else out.push(c)
    }
  }
  walk(root.namedChildren)
  return out.sort((a, b) => a.startIndex - b.startIndex)
}

const rl = createInterface({ input: process.stdin, crlfDelay: Infinity })
for await (const line of rl) {
  if (!line.trim()) continue
  let req
  try {
    req = JSON.parse(line)
    const tree = (await parserFor(req.lang)).parse(req.source)
    const root = tree.rootNode
    process.stdout.write(JSON.stringify({ id: req.id, ok: true, has_error: root.hasError, nodes: topLevel(root).map((c) => describe(c, 1)) }) + '\n')
    tree.delete()
  } catch (err) {
    process.stdout.write(JSON.stringify({ id: req?.id ?? null, ok: false, error: String(err?.message ?? err) }) + '\n')
  }
}

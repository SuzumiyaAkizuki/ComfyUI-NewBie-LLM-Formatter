// Migrate serialized graphs before LiteGraph restores nodes and connections.
export function migrateLayoutGraph(graph) {
  if (!Array.isArray(graph?.nodes)) return;
  const editors = new Set(graph.nodes.filter(n => n.type === "MOSS_Layout_Editor").map(n => String(n.id)));
  const removed = new Set();
  const links = (graph.links ?? []).filter(link => {
    const source = Array.isArray(link) ? link[1] : link.origin_id;
    const slot = Array.isArray(link) ? link[2] : link.origin_slot;
    if (!editors.has(String(source))) return true;
    if (slot === 4) { removed.add(Array.isArray(link) ? link[0] : link.id); return false; }
    if (slot === 0 || slot === 3) {
      if (Array.isArray(link)) { link[2] = 0; link[5] = "STRING"; }
      else { link.origin_slot = 0; link.type = "STRING"; }
    }
    return true;
  });
  if (Array.isArray(graph.links)) graph.links = links;
  for (const node of graph.nodes) {
    for (const input of node.inputs ?? []) {
      if (removed.has(input.link)) input.link = null;
      if (node.type === "LLM_Prompt_Formatter" && input.name === "layout") input.type = "STRING";
    }
    if (!editors.has(String(node.id))) continue;
    node.outputs = [["layout_prompr", "STRING"], ["width", "INT"], ["height", "INT"]].map(([name, type], index) => ({
      ...(node.outputs?.[index] ?? {}), name, localized_name:name, type,
      links:links.filter(l => String(Array.isArray(l) ? l[1] : l.origin_id) === String(node.id) && (Array.isArray(l) ? l[2] : l.origin_slot) === index)
        .map(l => Array.isArray(l) ? l[0] : l.id),
    }));
  }
}

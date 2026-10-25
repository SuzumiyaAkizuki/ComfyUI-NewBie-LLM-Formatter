// Presentation only: never deduplicate model reasoning or hide retry boundaries.
export function traceRows(events = []) {
  const rows = [];
  for (const event of events) {
    const row = { event:event.event, status:event.status, title:event.title || event.event || "运行状态", summary:String(event.summary || ""), callId:event.details?.tool_call_id };
    const previous = rows.at(-1);
    if (row.event !== "reasoning" && previous && previous.event === row.event &&
        previous.status === row.status && previous.title === row.title && previous.callId === row.callId &&
        (previous.requestSummary ?? previous.summary) === row.summary) continue;
    const round = value => value.match(/\bRound\s+(\d+)\b/i)?.[1];
    if (previous?.event === "round" && row.event === "request" &&
        round(previous.summary) && round(previous.summary) === round(row.summary)) {
      row.requestSummary = row.summary; row.summary = previous.summary; rows.pop();
    }
    rows.push(row);
  }
  return rows;
}

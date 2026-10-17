// Plain text helpers shared by several components.

export const sentence = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

export function when(ms: number | null | undefined): string {
  if (!ms) return ''
  return new Date(ms).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}

/** The API appends the facts, "Also checked" and "Not found" to the answer text; the UI shows those separately. */
export function splitAnswer(text: string) {
  const blocks = text.split('\n\n')
  return {
    prose: blocks.filter((b) => !/^(Facts from the graph:|Also checked:|Not found:)/.test(b)),
    notes: blocks.filter((b) => /^(Also checked:|Not found:)/.test(b)),
  }
}

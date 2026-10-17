// Citation intents from ontology.json, each with its own ink colour on the map and in tags.
// The colours are chosen so that the two "something is wrong" intents (criticizes, corrects) are the warm ones.
export const INTENTS: Record<string, { label: string; color: string; meaning: string }> = {
  extends: { label: 'extends', color: '#2c4bb5', meaning: 'builds directly on the cited method' },
  reproduces: { label: 'reproduces', color: '#0f7f74', meaning: 're-runs the cited work to check its results' },
  compares_against: { label: 'compares against', color: '#b7791f', meaning: 'reports the cited work as a baseline' },
  uses_method: { label: 'uses method', color: '#5b8fd6', meaning: 'uses the cited method as a component' },
  uses_dataset: { label: 'uses dataset', color: '#7a5bc7', meaning: 'evaluates on a dataset the cited work introduced' },
  supports: { label: 'supports', color: '#3f8a3a', meaning: 'presents evidence agreeing with the cited work' },
  criticizes: { label: 'criticizes', color: '#b8322a', meaning: 'argues the cited work is wrong or limited' },
  corrects: { label: 'corrects', color: '#a8327e', meaning: 'erratum or correction of the cited work' },
  background: { label: 'background', color: '#9aa3ab', meaning: 'general context only' },
}

const UNKNOWN = { label: 'not labelled yet', color: '#c4c9cf', meaning: 'the extractor has not labelled this citation' }

export const intentOf = (name: string | null | undefined) => INTENTS[name ?? ''] ?? { ...UNKNOWN, label: name || UNKNOWN.label }

/** "GraphFuse: Fusing Dense and Graph Retrieval" -> "GraphFuse" */
export const shortTitle = (title: string | null | undefined, fallback = '') =>
  (title ?? fallback).split(':')[0].trim() || fallback

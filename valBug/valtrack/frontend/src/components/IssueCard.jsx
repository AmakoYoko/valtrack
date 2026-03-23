import React from 'react'

export default function IssueCard({issue, onClick}){
  const badge = {
    open: 'bg-emerald-500/20 text-emerald-300',
    in_progress: 'bg-amber-500/20 text-amber-300',
    closed: 'bg-zinc-500/20 text-zinc-300'
  }[issue.status] || 'bg-zinc-700/20 text-zinc-300'

  return (
    <div onClick={onClick} className="p-4 rounded-2xl border border-white/10 bg-white/5 hover:bg-white/10 transition cursor-pointer">
      <div className="flex items-center gap-3">
        <span className={`text-xs px-2 py-0.5 rounded-full ${badge}`}>{issue.status}</span>
        <h3 className="font-semibold text-lg">{issue.title}</h3>
        <span className="ml-auto text-xs text-zinc-400">prio: {issue.priority}</span>
        {issue.url && <span title="Lien associé" className="text-xs px-2 py-0.5 rounded bg-white/10">🔗</span>}
      </div>
      {issue.description && <p className="text-zinc-300 mt-2 line-clamp-2">{issue.description}</p>}
    </div>
  )
}

import React, { useEffect, useState } from 'react'
import { api } from '../api'

export default function IssueDetail({id}){
  const [issue,setIssue] = useState(null)
  const [comment,setComment] = useState('')
   const [comments,setComments] = useState([])
    const load = async ()=>{
    const [i, c] = await Promise.all([
      api.get(`/issues/${id}`),
      api.get(`/issues/${id}/comments`)
    ])
    setIssue(i.data); setComments(c.data)
  }
  useEffect(()=>{ load() }, [id])
 const add = async ()=>{
   if(!comment.trim()) return
   await api.post('/issues/comments', {issue_id:id, body:comment})
   setComment('')
   await load()
 }
 const closeIssue = async ()=>{
   await api.post(`/issues/${id}/close`)
   await load()
 }
 const reopenIssue = async ()=>{
   await api.post(`/issues/${id}/reopen`)
   await load()
 }
 const deleteIssue = async ()=>{
   if(!confirm('Supprimer définitivement ce ticket ?')) return
   await api.delete(`/issues/${id}`)
   location.hash = 'issues'
 }
  if(!issue) return <div className="animate-pulse text-zinc-400">Chargement…</div>
  return (
    <div className="space-y-4">
      <div className="p-4 rounded-2xl border border-white/10 bg-white/5">
        <h2 className="text-2xl font-bold">{issue.title}</h2>
        <div className="flex items-center gap-2 mt-2">
          <span className="text-xs px-2 py-0.5 rounded-full bg-white/10">{issue.status}</span>
          <span className="text-xs text-zinc-400">prio: {issue.priority}</span>
          {issue.url && <a href={issue.url} target="_blank" rel="noreferrer" className="text-xs underline ml-auto">Ouvrir le lien 🔗</a>}
        </div>
        <p className="text-zinc-300 mt-3 whitespace-pre-wrap">{issue.description || '—'}</p>
        <div className="mt-4 flex gap-2">
          {issue.status !== 'closed'
            ? <button onClick={closeIssue} className="px-3 py-1 rounded-xl bg-emerald-500 text-black font-semibold">Clôturer</button>
            : <button onClick={reopenIssue} className="px-3 py-1 rounded-xl bg-amber-400 text-black font-semibold">Rouvrir</button>}
          <button onClick={deleteIssue} className="px-3 py-1 rounded-xl bg-red-500 text-white">Supprimer</button>
        </div>
      </div>
      <div className="p-4 rounded-2xl border border-white/10 bg-white/5">
        <h3 className="font-semibold mb-2">Commentaires</h3>
        <div className="space-y-2 mb-3">
          {comments.length===0 && <div className="text-zinc-400 text-sm">Aucun commentaire.</div>}
          {comments.map(c=>(
            <div key={c.id} className="p-3 rounded-xl bg-zinc-900 border border-white/10">
              <div className="text-sm text-zinc-400">{new Date(c.created_at).toLocaleString?.() || c.created_at}</div>
              <div className="mt-1 whitespace-pre-wrap">{c.body}</div>
            </div>
          ))}
        </div>
        <div className="flex gap-2">
          <input value={comment} onChange={e=>setComment(e.target.value)} className="flex-1 bg-zinc-900 border border-white/10 rounded-xl p-3" placeholder="Votre message…" />
          <button onClick={add} className="bg-white text-black font-semibold px-4 py-2 rounded-xl">Envoyer</button>
        </div>
      </div>
      <div className="p-4 rounded-2xl border border-white/10 bg-white/5">
        <h3 className="font-semibold mb-2">Ajouter un commentaire</h3>
        <div className="flex gap-2">
          <input value={comment} onChange={e=>setComment(e.target.value)} className="flex-1 bg-zinc-900 border border-white/10 rounded-xl p-3" placeholder="Votre message…" />
          <button onClick={add} className="bg-white text-black font-semibold px-4 py-2 rounded-xl">Envoyer</button>
        </div>
      </div>
    </div>
  )
}

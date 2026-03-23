import React, { useState } from 'react'
import { api } from '../api'

export default function NewIssue(){
  const [title,setTitle] = useState('')
  const [description,setDescription] = useState('')
  const [url,setUrl] = useState('')
  const [priority,setPriority] = useState('normal')
  const submit = async (e)=>{
    e.preventDefault()
    await api.post('/issues', {title, description, priority, url: url || null})
    location.hash = 'issues'
  }
  return (
    <form onSubmit={submit} className="max-w-xl space-y-3">
      <input className="w-full bg-zinc-900 border border-white/10 rounded-xl p-3" placeholder="Titre" value={title} onChange={e=>setTitle(e.target.value)} />
      <input className="w-full bg-zinc-900 border border-white/10 rounded-xl p-3" placeholder="URL (facultatif)" value={url} onChange={e=>setUrl(e.target.value)} />

      <textarea className="w-full bg-zinc-900 border border-white/10 rounded-xl p-3" rows="6" placeholder="Description" value={description} onChange={e=>setDescription(e.target.value)} />
      <div className="flex gap-2 items-center">
        <label>Priorité</label>
        <select className="bg-zinc-900 border border-white/10 rounded-lg px-3 py-2" value={priority} onChange={e=>setPriority(e.target.value)}>
          <option value="low">Basse</option>
          <option value="normal">Normale</option>
          <option value="high">Haute</option>
          <option value="urgent">Urgente</option>
        </select>
      </div>
      <button className="bg-white text-black font-semibold px-4 py-2 rounded-xl">Créer</button>
    </form>
  )
}

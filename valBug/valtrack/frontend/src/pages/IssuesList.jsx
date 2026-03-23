import React, { useEffect, useState } from 'react'
import { api } from '../api'
import IssueCard from '../components/IssueCard'

export default function IssuesList(){
  const [items,setItems] = useState(null)
  useEffect(()=>{ api.get('/issues').then(r=> setItems(r.data)) }, [])
  if(!items) return <div className="animate-pulse text-zinc-400">Chargement…</div>
  return (
    <div className="space-y-3">
      {items.map(i=> <IssueCard key={i.id} issue={i} onClick={()=> location.hash = `issue/${i.id}`} />)}
      {items.length===0 && <div className="text-zinc-400">Aucune issue pour l’instant.</div>}
    </div>
  )
}

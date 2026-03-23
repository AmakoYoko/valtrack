import React, { useEffect, useState } from 'react'
import { api, setWorkspaceHeader } from '../api'

export default function Topbar({onNavigate}){
  const [workspaces,setWorkspaces] = useState([])
  const [current,setCurrent] = useState('demo')

  useEffect(()=>{
    api.get('/workspaces').then(r=> setWorkspaces(r.data)).catch(()=>{})
  }, [])

  useEffect(()=>{ setWorkspaceHeader(current) }, [current])

  return (
    <header className="border-b border-white/10 bg-zinc-950/60 backdrop-blur sticky top-0 z-10">
      <div className="max-w-5xl mx-auto flex items-center gap-4 p-3">
        <div className="font-extrabold text-xl">{window.__ENV__?.PUBLIC_BRAND || 'ValTrack'}</div>
        <nav className="flex items-center gap-2 text-sm">
          <a className="px-3 py-1 rounded-lg hover:bg-white/10" onClick={()=>onNavigate('issues')}>Issues</a>
          <a className="px-3 py-1 rounded-lg hover:bg-white/10" onClick={()=>onNavigate('new')}>Nouvelle issue</a>
        </nav>
        <div className="ml-auto">
          <select className="bg-zinc-900 border border-white/10 rounded-lg px-3 py-1" value={current} onChange={e=>setCurrent(e.target.value)}>
            <option value="demo">demo</option>
            {workspaces.map(w=> <option key={w.id} value={w.slug}>{w.name}</option>)}
          </select>
        </div>
      </div>
    </header>
  )
}

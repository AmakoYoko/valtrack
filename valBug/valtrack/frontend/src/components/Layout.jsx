import React, { useEffect } from 'react'
import Topbar from './Topbar'

export default function Layout({children, onNavigate}){
  useEffect(()=>{ document.title = (window.__ENV__?.PUBLIC_BRAND || 'ValTrack') + ' — Bug Tracker' }, [])
  return (
    <div className="min-h-screen">
      <Topbar onNavigate={onNavigate} />
      <main className="max-w-5xl mx-auto p-4 md:p-8 space-y-6">{children}</main>
    </div>
  )
}

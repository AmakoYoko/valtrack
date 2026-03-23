import React, { useEffect, useState } from 'react'
import Layout from './components/Layout'
import IssuesList from './pages/IssuesList'
import NewIssue from './pages/NewIssue'
import IssueDetail from './pages/IssueDetail'

export default function App(){
  const [route, setRoute] = useState(window.location.hash.slice(1) || 'issues')
  useEffect(()=>{
    const onHash = () => setRoute(window.location.hash.slice(1) || 'issues')
    window.addEventListener('hashchange', onHash)
    return ()=> window.removeEventListener('hashchange', onHash)
  }, [])

  let page = <IssuesList/>
  if(route.startsWith('new')) page = <NewIssue/>
  if(route.startsWith('issue/')) page = <IssueDetail id={route.split('/')[1]} />

  return <Layout onNavigate={(r)=>location.hash = r}>{page}</Layout>
}

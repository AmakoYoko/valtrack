import axios from 'axios'

const API_BASE = (window.__ENV__ && window.__ENV__.PUBLIC_API_BASE) || '/api'

export const api = axios.create({
  baseURL: API_BASE,
})

export function setWorkspaceHeader(slug){
  api.defaults.headers.common['X-Workspace'] = slug
}

import { createContext } from 'react'
import type { AuthUser } from '../types'

export type AuthContextValue = {
  user: AuthUser
  setRole: (role: AuthUser['role']) => void
}

export const defaultUser: AuthUser = {
  name: 'Rogério Mind',
  role: 'Administrador',
  avatarUrl: 'https://i.pravatar.cc/80?img=12',
}

export const AuthContext = createContext<AuthContextValue | undefined>(undefined)

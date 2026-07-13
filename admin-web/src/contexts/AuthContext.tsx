import { useEffect, useMemo, useState } from 'react'
import { userService } from '../services/userService'
import type { AuthUser } from '../types'
import { AuthContext, defaultUser } from './AuthContextValue'

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser>(defaultUser)

  useEffect(() => {
    userService.me().then(setUser).catch(() => setUser(defaultUser))
  }, [])

  const value = useMemo(
    () => ({
      user,
      setRole: (role: AuthUser['role']) => {
        window.localStorage.setItem('ia-pmo-role', role)
        setUser((current) => ({ ...current, role }))
      },
    }),
    [user],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

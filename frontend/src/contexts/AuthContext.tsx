import React, { createContext, useContext, useState, useEffect, useCallback } from 'react'
import type { User } from '../types'
import { authApi } from '../services/api'

interface AuthContextType {
  user: User | null
  isLoading: boolean
  isAuthenticated: boolean
  login: (username: string, password: string) => Promise<User>
  logout: () => void
}

const AuthContext = createContext<AuthContextType | null>(null)

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    const initAuth = async () => {
      // Remove sessions created by older versions that were shared across tabs.
      localStorage.removeItem('access_token')
      localStorage.removeItem('user')

      const token = sessionStorage.getItem('access_token')
      if (token) {
        try {
          const res = await authApi.getMe()
          if (res.success) {
            setUser(res.data)
          }
        } catch {
          sessionStorage.removeItem('access_token')
          setUser(null)
        }
      }
      setIsLoading(false)
    }
    initAuth()
  }, [])

  const login = useCallback(async (username: string, password: string) => {
    const res = await authApi.login(username, password)
    if (res.success) {
      sessionStorage.setItem('access_token', res.data.access_token)
      setUser(res.data.user)
      return res.data.user
    } else {
      throw new Error(res.message || 'Đăng nhập thất bại')
    }
  }, [])

  const logout = useCallback(() => {
    sessionStorage.removeItem('access_token')
    setUser(null)
    window.location.href = '/login'
  }, [])

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated: !!user,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export const useAuthContext = () => {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuthContext phải được dùng bên trong AuthProvider')
  return ctx
}

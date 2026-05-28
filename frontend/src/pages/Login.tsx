import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Scan, Eye, EyeOff, AlertCircle, Lock } from 'lucide-react'
import { useAuth } from '../hooks/useAuth'

const Login: React.FC = () => {
  const { login } = useAuth()
  const navigate = useNavigate()

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!username.trim() || !password.trim()) {
      setError('Vui lòng nhập đầy đủ thông tin đăng nhập.')
      return
    }
    setError('')
    setIsLoading(true)
    try {
      const user = await login(username.trim(), password)
      if (user.role === 'admin') {
        navigate('/admin/dashboard')
      } else {
        navigate('/my/dashboard')
      }
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message)
      } else {
        setError('Đăng nhập thất bại, vui lòng thử lại.')
      }
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-mint-50 via-white to-teal-50 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Card */}
        <div className="bg-white rounded-2xl shadow-xl overflow-hidden">
          {/* Header */}
          <div className="bg-gradient-to-r from-mint-600 to-teal-700 px-8 py-10 text-center">
            <div className="w-16 h-16 bg-white bg-opacity-20 rounded-2xl flex items-center justify-center mx-auto mb-4">
              <Scan size={32} className="text-white" />
            </div>
            <h1 className="text-2xl font-bold text-white mb-1">Hệ Thống Chấm Công</h1>
            <p className="text-mint-100 text-sm">Quản lý Nhân sự & Nhận diện Khuôn mặt</p>
          </div>

          {/* Form */}
          <div className="px-8 py-8">
            <h2 className="text-xl font-semibold text-gray-800 mb-6 text-center">
              Đăng nhập hệ thống
            </h2>

            {error && (() => {
              const isLocked = error.includes('bị khóa')
              return (
                <div className={`flex items-start gap-3 rounded-lg px-4 py-3 mb-5 border ${
                  isLocked
                    ? 'bg-orange-50 border-orange-200'
                    : 'bg-red-50 border-red-200'
                }`}>
                  {isLocked
                    ? <Lock size={16} className="text-orange-500 mt-0.5 flex-shrink-0" />
                    : <AlertCircle size={16} className="text-red-500 mt-0.5 flex-shrink-0" />
                  }
                  <p className={`text-sm ${isLocked ? 'text-orange-700' : 'text-red-700'}`}>{error}</p>
                </div>
              )
            })()}

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">
                  Tên đăng nhập
                </label>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="Nhập tên đăng nhập"
                  className="input-field"
                  autoComplete="username"
                  autoFocus
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">
                  Mật khẩu
                </label>
                <div className="relative">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Nhập mật khẩu"
                    className="input-field pr-10"
                    autoComplete="current-password"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                  >
                    {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
              </div>

              <button
                type="submit"
                disabled={isLoading}
                className="w-full btn-primary py-3 text-base mt-2"
              >
                {isLoading ? (
                  <span className="flex items-center justify-center gap-2">
                    <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    Đang đăng nhập...
                  </span>
                ) : (
                  'Đăng nhập'
                )}
              </button>
            </form>

            <p className="text-center text-xs text-gray-400 mt-6">
              Liên hệ quản trị viên nếu quên mật khẩu
            </p>
          </div>
        </div>

        <p className="text-center text-xs text-gray-400 mt-4">
          © 2026 Hệ thống Quản lý Nhân sự & Chấm công
        </p>
      </div>
    </div>
  )
}

export default Login

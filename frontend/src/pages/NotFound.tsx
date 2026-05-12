import React from 'react'
import { Link } from 'react-router-dom'
import { Home, AlertTriangle } from 'lucide-react'
import { useAuth } from '../hooks/useAuth'

const NotFound: React.FC = () => {
  const { user } = useAuth()
  const homeLink = user?.role === 'admin' ? '/admin/dashboard' : '/my/dashboard'

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
      <div className="text-center max-w-md">
        <div className="w-20 h-20 bg-yellow-100 rounded-full flex items-center justify-center mx-auto mb-6">
          <AlertTriangle size={36} className="text-yellow-500" />
        </div>
        <h1 className="text-6xl font-bold text-gray-200 mb-2">404</h1>
        <h2 className="text-2xl font-semibold text-gray-800 mb-3">Trang không tìm thấy</h2>
        <p className="text-gray-500 mb-8">
          Trang bạn đang tìm kiếm không tồn tại hoặc đã bị xóa.
        </p>
        <Link
          to={homeLink}
          className="inline-flex items-center gap-2 btn-primary"
        >
          <Home size={18} />
          Về trang chủ
        </Link>
      </div>
    </div>
  )
}

export default NotFound

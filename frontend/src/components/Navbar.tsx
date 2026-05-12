import React from 'react'
import { LogOut, Menu, User } from 'lucide-react'
import { useAuth } from '../hooks/useAuth'
import NotificationDropdown from './NotificationDropdown'

interface NavbarProps {
  onMenuClick: () => void
}

const Navbar: React.FC<NavbarProps> = ({ onMenuClick }) => {
  const { user, logout } = useAuth()

  return (
    <header className="h-16 bg-white border-b border-gray-200 flex items-center justify-between px-4 lg:px-6 sticky top-0 z-30">
      <div className="flex items-center gap-3">
        <button
          onClick={onMenuClick}
          className="lg:hidden p-2 rounded-lg hover:bg-gray-100 text-gray-500 transition-colors"
        >
          <Menu size={20} />
        </button>
        <div className="hidden lg:block">
          <h2 className="text-sm text-gray-500">
            {new Date().toLocaleDateString('vi-VN', {
              weekday: 'long',
              year: 'numeric',
              month: 'long',
              day: 'numeric',
            })}
          </h2>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <NotificationDropdown />

        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-mint-600 rounded-full flex items-center justify-center">
            <User size={16} className="text-white" />
          </div>
          <div className="hidden md:block text-right">
            <p className="text-sm font-medium text-gray-900 leading-tight">
              {user?.full_name || user?.username}
            </p>
            <p className="text-xs text-gray-500">
              {user?.role === 'admin' ? 'Quản trị viên' : 'Nhân viên'}
            </p>
          </div>
        </div>

        <button
          onClick={logout}
          className="flex items-center gap-2 text-gray-500 hover:text-red-600 hover:bg-red-50 px-3 py-2 rounded-lg text-sm transition-colors"
        >
          <LogOut size={16} />
          <span className="hidden md:inline">Đăng xuất</span>
        </button>
      </div>
    </header>
  )
}

export default Navbar

import React from 'react'
import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  Users,
  Building2,
  Scan,
  CreditCard,
  Clock,
  FileText,
  BarChart3,
  Home,
  User,
  X,
  ChevronRight,
} from 'lucide-react'
import { useAuth } from '../hooks/useAuth'

interface SidebarProps {
  isOpen: boolean
  onClose: () => void
}

const adminNavItems = [
  { to: '/admin/dashboard', label: 'Tổng quan', icon: LayoutDashboard },
  { to: '/admin/employees', label: 'Nhân viên', icon: Users },
  { to: '/admin/departments', label: 'Phòng ban', icon: Building2 },
  { to: '/admin/face', label: 'Khuôn mặt', icon: Scan },
  { to: '/admin/rfid', label: 'Thẻ RFID', icon: CreditCard },
  { to: '/admin/attendance', label: 'Chấm công', icon: Clock },
  { to: '/admin/leave', label: 'Đơn từ', icon: FileText },
  { to: '/admin/reports', label: 'Báo cáo', icon: BarChart3 },
]

const employeeNavItems = [
  { to: '/my/dashboard', label: 'Tổng quan', icon: Home },
  { to: '/my/attendance', label: 'Chấm công của tôi', icon: Clock },
  { to: '/my/requests', label: 'Đơn từ', icon: FileText },
  { to: '/my/profile', label: 'Hồ sơ', icon: User },
]

const Sidebar: React.FC<SidebarProps> = ({ isOpen, onClose }) => {
  const { user } = useAuth()
  const navItems = user?.role === 'admin' ? adminNavItems : employeeNavItems

  return (
    <>
      {/* Mobile overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black bg-opacity-50 z-40 lg:hidden"
          onClick={onClose}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed top-0 left-0 h-full w-64 bg-gray-900 text-white z-50 flex flex-col transition-transform duration-300 lg:translate-x-0 lg:relative lg:z-auto ${
          isOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        {/* Logo */}
        <div className="flex items-center justify-between h-16 px-5 border-b border-gray-700">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-mint-600 rounded-lg flex items-center justify-center">
              <Scan size={18} />
            </div>
            <div>
              <p className="text-sm font-bold text-white leading-tight">HR System</p>
              <p className="text-xs text-gray-400">Quản lý Nhân sự</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="lg:hidden text-gray-400 hover:text-white p-1 rounded transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* User Info */}
        <div className="px-5 py-4 border-b border-gray-700">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 bg-mint-500 rounded-full flex items-center justify-center flex-shrink-0">
              <User size={16} />
            </div>
            <div className="min-w-0">
              <p className="text-sm font-medium text-white truncate">
                {user?.full_name || user?.username}
              </p>
              <p className="text-xs text-gray-400">
                {user?.role === 'admin' ? 'Quản trị viên' : 'Nhân viên'}
              </p>
            </div>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto px-3 py-3">
          <ul className="space-y-1">
            {navItems.map((item) => {
              const Icon = item.icon
              return (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    onClick={onClose}
                    className={({ isActive }) =>
                      `flex items-center justify-between gap-3 px-3 py-2.5 rounded-lg text-sm transition-all duration-150 group ${
                        isActive
                          ? 'bg-mint-600 text-white'
                          : 'text-gray-400 hover:bg-gray-800 hover:text-white'
                      }`
                    }
                  >
                    <div className="flex items-center gap-3">
                      <Icon size={18} />
                      <span className="font-medium">{item.label}</span>
                    </div>
                    <ChevronRight size={14} className="opacity-0 group-hover:opacity-100 transition-opacity" />
                  </NavLink>
                </li>
              )
            })}
          </ul>
        </nav>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-gray-700">
          <p className="text-xs text-gray-500 text-center">v1.0 © 2026 KTPM K21A</p>
        </div>
      </aside>
    </>
  )
}

export default Sidebar

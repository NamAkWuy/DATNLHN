import React, { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Edit2, Save, X, Camera, User, Mail, Phone, Briefcase, Building2, CreditCard, Scan } from 'lucide-react'
import { employeeApi, resolveAssetUrl } from '../../services/api'
import { useAuth } from '../../hooks/useAuth'
import PageTitle from '../../components/PageTitle'
import LoadingSpinner from '../../components/LoadingSpinner'
import StatusBadge from '../../components/StatusBadge'

const Profile: React.FC = () => {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [isEditing, setIsEditing] = useState(false)
  const [editForm, setEditForm] = useState({ phone: '', email: '' })
  const [editErrors, setEditErrors] = useState<{ phone?: string; email?: string }>({})

  const { data, isLoading } = useQuery({
    queryKey: ['my-profile', user?.employee_id],
    queryFn: () => employeeApi.getById(user!.employee_id),
    enabled: !!user?.employee_id,
  })

  const updateMutation = useMutation({
    mutationFn: (formData: { phone: string; email: string }) =>
      employeeApi.update(user!.employee_id, formData),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['my-profile'] })
      setIsEditing(false)
    },
  })

  const avatarMutation = useMutation({
    mutationFn: (file: File) => employeeApi.uploadAvatar(user!.employee_id, file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['my-profile'] })
    },
  })

  const employee = data?.data

  const startEdit = () => {
    setEditForm({
      phone: employee?.phone || '',
      email: employee?.email || '',
    })
    setEditErrors({})
    setIsEditing(true)
  }

  const cancelEdit = () => {
    setIsEditing(false)
    setEditErrors({})
  }

  const validateEdit = () => {
    const errors: { phone?: string; email?: string } = {}
    if (editForm.email && !/\S+@\S+\.\S+/.test(editForm.email)) {
      errors.email = 'Email không hợp lệ'
    }
    setEditErrors(errors)
    return Object.keys(errors).length === 0
  }

  const handleSave = () => {
    if (!validateEdit()) return
    updateMutation.mutate(editForm)
  }

  const handleAvatarChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      avatarMutation.mutate(file)
    }
    // Reset để chọn lại cùng 1 file vẫn trigger onChange
    e.target.value = ''
  }

  if (isLoading) {
    return (
      <div className="flex justify-center py-16">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (!employee) {
    return (
      <div className="text-center py-16 text-gray-400">
        Không thể tải thông tin hồ sơ
      </div>
    )
  }

  const infoItems = [
    { icon: <Mail size={16} />, label: 'Email', value: employee.email, field: 'email' as const },
    { icon: <Phone size={16} />, label: 'Số điện thoại', value: employee.phone || '—', field: 'phone' as const },
    { icon: <Briefcase size={16} />, label: 'Chức vụ', value: employee.position, field: null },
    { icon: <Building2 size={16} />, label: 'Phòng ban', value: employee.department?.name || '—', field: null },
    { icon: <CreditCard size={16} />, label: 'Mã nhân viên', value: employee.employee_code, field: null },
  ]

  return (
    <div className="max-w-4xl">
      <PageTitle title="Hồ sơ của tôi" />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Avatar + Basic */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 text-center">
          <div className="relative inline-block mb-4">
            <div className="w-28 h-28 rounded-full bg-mint-100 flex items-center justify-center mx-auto overflow-hidden">
              {employee.avatar_url ? (
                <img
                  src={`${resolveAssetUrl(employee.avatar_url)}?t=${encodeURIComponent(employee.updated_at || '')}`}
                  alt={employee.full_name}
                  className="w-full h-full object-cover"
                />
              ) : (
                <User size={48} className="text-mint-400" />
              )}
            </div>
            <button
              onClick={() => fileInputRef.current?.click()}
              className="absolute bottom-0 right-0 w-8 h-8 bg-mint-600 rounded-full flex items-center justify-center text-white hover:bg-mint-700 transition-colors shadow-md"
              title="Thay đổi ảnh đại diện"
            >
              {avatarMutation.isPending ? (
                <LoadingSpinner size="sm" className="border-white" />
              ) : (
                <Camera size={14} />
              )}
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={handleAvatarChange}
            />
          </div>

          {avatarMutation.isError && (
            <div className="mb-2 bg-red-50 border border-red-200 rounded-lg p-2">
              <p className="text-red-700 text-xs">{avatarMutation.error?.message || 'Tải ảnh thất bại'}</p>
            </div>
          )}

          <h2 className="text-xl font-bold text-gray-900">{employee.full_name}</h2>
          <p className="text-gray-500 text-sm mt-1">{employee.position}</p>
          <div className="mt-2">
            <StatusBadge status={employee.status} />
          </div>

          <div className="mt-4 pt-4 border-t border-gray-100 space-y-2">
            <div className="flex items-center justify-center gap-2 text-sm">
              <Scan size={14} className={employee.has_face ? 'text-green-500' : 'text-gray-300'} />
              <span className={employee.has_face ? 'text-green-600' : 'text-gray-400'}>
                {employee.has_face ? 'Đã đăng ký khuôn mặt' : 'Chưa đăng ký khuôn mặt'}
              </span>
            </div>
            <div className="flex items-center justify-center gap-2 text-sm">
              <CreditCard size={14} className={employee.has_rfid ? 'text-green-500' : 'text-gray-300'} />
              <span className={employee.has_rfid ? 'text-green-600' : 'text-gray-400'}>
                {employee.has_rfid ? 'Có thẻ RFID' : 'Chưa có thẻ RFID'}
              </span>
            </div>
          </div>
        </div>

        {/* Details */}
        <div className="lg:col-span-2 space-y-4">
          {/* Personal Info */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-semibold text-gray-900">Thông tin cá nhân</h3>
              {!isEditing ? (
                <button onClick={startEdit} className="flex items-center gap-1.5 text-sm text-mint-600 hover:bg-mint-50 px-3 py-1.5 rounded-lg transition-colors">
                  <Edit2 size={14} />
                  Chỉnh sửa
                </button>
              ) : (
                <div className="flex gap-2">
                  <button onClick={cancelEdit} className="flex items-center gap-1.5 text-sm text-gray-500 hover:bg-gray-100 px-3 py-1.5 rounded-lg transition-colors">
                    <X size={14} />
                    Hủy
                  </button>
                  <button onClick={handleSave} disabled={updateMutation.isPending} className="flex items-center gap-1.5 text-sm btn-primary py-1.5 px-3">
                    {updateMutation.isPending ? <LoadingSpinner size="sm" /> : <><Save size={14} /> Lưu</>}
                  </button>
                </div>
              )}
            </div>

            <div className="space-y-4">
              {infoItems.map((item) => (
                <div key={item.label} className="flex items-start gap-3">
                  <div className="w-8 h-8 bg-gray-100 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5 text-gray-500">
                    {item.icon}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-gray-400 mb-0.5">{item.label}</p>
                    {isEditing && item.field ? (
                      <div>
                        <input
                          type={item.field === 'email' ? 'email' : 'text'}
                          className={`input-field text-sm py-1.5 ${editErrors[item.field] ? 'border-red-400' : ''}`}
                          value={editForm[item.field]}
                          onChange={(e) => setEditForm({ ...editForm, [item.field!]: e.target.value })}
                        />
                        {editErrors[item.field] && (
                          <p className="text-red-500 text-xs mt-1">{editErrors[item.field]}</p>
                        )}
                      </div>
                    ) : (
                      <p className="text-sm font-medium text-gray-800">{item.value}</p>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {updateMutation.isError && (
              <div className="mt-3 bg-red-50 border border-red-200 rounded-lg p-3">
                <p className="text-red-700 text-sm">{updateMutation.error?.message || 'Cập nhật thất bại'}</p>
              </div>
            )}
          </div>

          {/* Account Info */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
            <h3 className="text-base font-semibold text-gray-900 mb-4">Thông tin tài khoản</h3>
            <div className="space-y-3">
              <div className="flex items-center justify-between py-2 border-b border-gray-50">
                <span className="text-sm text-gray-500">Tên đăng nhập</span>
                <span className="text-sm font-medium text-gray-800 font-mono">{user?.username}</span>
              </div>
              <div className="flex items-center justify-between py-2 border-b border-gray-50">
                <span className="text-sm text-gray-500">Phân quyền</span>
                <span className="text-sm font-medium text-gray-800">
                  {user?.role === 'admin' ? 'Quản trị viên' : 'Nhân viên'}
                </span>
              </div>
              <div className="flex items-center justify-between py-2">
                <span className="text-sm text-gray-500">Ngày tạo tài khoản</span>
                <span className="text-sm text-gray-600">
                  {employee.created_at
                    ? new Date(employee.created_at).toLocaleDateString('vi-VN')
                    : '—'}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default Profile

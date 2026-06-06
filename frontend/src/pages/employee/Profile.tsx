import React, { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Edit2, Save, X, Camera, User, Mail, Phone, Briefcase, Building2, CreditCard, Scan, KeyRound, Eye, EyeOff, CheckCircle } from 'lucide-react'
import { authApi, employeeApi, resolveAssetUrl } from '../../services/api'
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

  // Đổi mật khẩu
  const [showPwForm, setShowPwForm] = useState(false)
  const [pwForm, setPwForm] = useState({ old_password: '', new_password: '', confirm_password: '' })
  const [pwErrors, setPwErrors] = useState<{ old_password?: string; new_password?: string; confirm_password?: string }>({})
  const [pwReveal, setPwReveal] = useState({ old: false, new: false, confirm: false })
  const [pwSuccess, setPwSuccess] = useState(false)

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

  const changePasswordMutation = useMutation({
    mutationFn: (data: { old_password: string; new_password: string }) =>
      authApi.changePassword(data.old_password, data.new_password),
    onSuccess: () => {
      setPwSuccess(true)
      setPwForm({ old_password: '', new_password: '', confirm_password: '' })
      setPwErrors({})
      // Tự ẩn form sau 2 giây để user thấy thông báo thành công
      setTimeout(() => {
        setShowPwForm(false)
        setPwSuccess(false)
      }, 2000)
    },
  })

  const openPwForm = () => {
    setShowPwForm(true)
    setPwForm({ old_password: '', new_password: '', confirm_password: '' })
    setPwErrors({})
    setPwSuccess(false)
    changePasswordMutation.reset()
  }

  const cancelPwForm = () => {
    setShowPwForm(false)
    setPwErrors({})
    setPwSuccess(false)
    changePasswordMutation.reset()
  }

  const validatePwForm = (): boolean => {
    const errors: typeof pwErrors = {}
    if (!pwForm.old_password) errors.old_password = 'Bắt buộc'
    if (!pwForm.new_password) errors.new_password = 'Bắt buộc'
    else if (pwForm.new_password.length < 6) errors.new_password = 'Tối thiểu 6 ký tự'
    else if (pwForm.new_password === pwForm.old_password)
      errors.new_password = 'Mật khẩu mới phải khác mật khẩu cũ'
    if (pwForm.confirm_password !== pwForm.new_password)
      errors.confirm_password = 'Xác nhận mật khẩu không khớp'
    setPwErrors(errors)
    return Object.keys(errors).length === 0
  }

  const handleChangePassword = () => {
    if (!validatePwForm()) return
    changePasswordMutation.mutate({
      old_password: pwForm.old_password,
      new_password: pwForm.new_password,
    })
  }

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

          {/* Đổi mật khẩu */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-semibold text-gray-900 flex items-center gap-2">
                <KeyRound size={16} className="text-mint-600" />
                Mật khẩu
              </h3>
              {!showPwForm ? (
                <button
                  onClick={openPwForm}
                  className="flex items-center gap-1.5 text-sm text-mint-600 hover:bg-mint-50 px-3 py-1.5 rounded-lg transition-colors"
                >
                  <Edit2 size={14} />
                  Đổi mật khẩu
                </button>
              ) : (
                <button
                  onClick={cancelPwForm}
                  className="flex items-center gap-1.5 text-sm text-gray-500 hover:bg-gray-100 px-3 py-1.5 rounded-lg transition-colors"
                >
                  <X size={14} />
                  Hủy
                </button>
              )}
            </div>

            {!showPwForm ? (
              <p className="text-sm text-gray-500">
                Để bảo mật, nên đổi mật khẩu sau lần đăng nhập đầu hoặc sau khi admin reset mật khẩu cho bạn.
              </p>
            ) : pwSuccess ? (
              <div className="text-center py-4">
                <CheckCircle size={40} className="text-green-500 mx-auto mb-2" />
                <p className="text-green-700 font-medium">Đổi mật khẩu thành công!</p>
                <p className="text-gray-500 text-sm mt-1">Lần đăng nhập tiếp theo hãy dùng mật khẩu mới.</p>
              </div>
            ) : (
              <div className="space-y-4">
                {/* Mật khẩu hiện tại */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Mật khẩu hiện tại <span className="text-red-500">*</span>
                  </label>
                  <div className="relative">
                    <input
                      type={pwReveal.old ? 'text' : 'password'}
                      className={`input-field pr-10 ${pwErrors.old_password ? 'border-red-400' : ''}`}
                      value={pwForm.old_password}
                      onChange={(e) => setPwForm({ ...pwForm, old_password: e.target.value })}
                      autoComplete="current-password"
                    />
                    <button
                      type="button"
                      onClick={() => setPwReveal({ ...pwReveal, old: !pwReveal.old })}
                      className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-400 hover:text-gray-600"
                    >
                      {pwReveal.old ? <EyeOff size={16} /> : <Eye size={16} />}
                    </button>
                  </div>
                  {pwErrors.old_password && (
                    <p className="text-red-500 text-xs mt-1">{pwErrors.old_password}</p>
                  )}
                </div>

                {/* Mật khẩu mới */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Mật khẩu mới <span className="text-red-500">*</span>
                  </label>
                  <div className="relative">
                    <input
                      type={pwReveal.new ? 'text' : 'password'}
                      className={`input-field pr-10 ${pwErrors.new_password ? 'border-red-400' : ''}`}
                      value={pwForm.new_password}
                      onChange={(e) => setPwForm({ ...pwForm, new_password: e.target.value })}
                      autoComplete="new-password"
                      placeholder="Tối thiểu 6 ký tự"
                    />
                    <button
                      type="button"
                      onClick={() => setPwReveal({ ...pwReveal, new: !pwReveal.new })}
                      className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-400 hover:text-gray-600"
                    >
                      {pwReveal.new ? <EyeOff size={16} /> : <Eye size={16} />}
                    </button>
                  </div>
                  {pwErrors.new_password && (
                    <p className="text-red-500 text-xs mt-1">{pwErrors.new_password}</p>
                  )}
                </div>

                {/* Xác nhận mật khẩu mới */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Xác nhận mật khẩu mới <span className="text-red-500">*</span>
                  </label>
                  <div className="relative">
                    <input
                      type={pwReveal.confirm ? 'text' : 'password'}
                      className={`input-field pr-10 ${pwErrors.confirm_password ? 'border-red-400' : ''}`}
                      value={pwForm.confirm_password}
                      onChange={(e) => setPwForm({ ...pwForm, confirm_password: e.target.value })}
                      autoComplete="new-password"
                    />
                    <button
                      type="button"
                      onClick={() => setPwReveal({ ...pwReveal, confirm: !pwReveal.confirm })}
                      className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-400 hover:text-gray-600"
                    >
                      {pwReveal.confirm ? <EyeOff size={16} /> : <Eye size={16} />}
                    </button>
                  </div>
                  {pwErrors.confirm_password && (
                    <p className="text-red-500 text-xs mt-1">{pwErrors.confirm_password}</p>
                  )}
                </div>

                {changePasswordMutation.isError && (
                  <div className="bg-red-50 border border-red-200 rounded-lg p-3">
                    <p className="text-red-700 text-sm">
                      {changePasswordMutation.error?.message || 'Đổi mật khẩu thất bại'}
                    </p>
                  </div>
                )}

                <div className="flex justify-end gap-2 pt-1">
                  <button onClick={cancelPwForm} className="btn-secondary">
                    Hủy
                  </button>
                  <button
                    onClick={handleChangePassword}
                    disabled={changePasswordMutation.isPending}
                    className="btn-primary flex items-center gap-2"
                  >
                    {changePasswordMutation.isPending ? (
                      <LoadingSpinner size="sm" />
                    ) : (
                      <>
                        <Save size={14} /> Lưu mật khẩu mới
                      </>
                    )}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default Profile

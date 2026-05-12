import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Search, Edit2, Trash2, CheckCircle, XCircle } from 'lucide-react'
import { employeeApi, departmentApi } from '../../services/api'
import type { Employee, Department } from '../../types'
import PageTitle from '../../components/PageTitle'
import StatusBadge from '../../components/StatusBadge'
import Modal from '../../components/Modal'
import LoadingSpinner from '../../components/LoadingSpinner'
import Pagination from '../../components/Pagination'

interface EmployeeForm {
  full_name: string
  email: string
  phone: string
  position: string
  department_id: string
  password: string
  role: 'admin' | 'employee'
  status: 'active' | 'inactive'
}

const defaultForm: EmployeeForm = {
  full_name: '',
  email: '',
  phone: '',
  position: '',
  department_id: '',
  password: '',
  role: 'employee',
  status: 'active',
}

const Employees: React.FC = () => {
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [filterDept, setFilterDept] = useState('')
  const [filterStatus, setFilterStatus] = useState('')

  const [showModal, setShowModal] = useState(false)
  const [editEmployee, setEditEmployee] = useState<Employee | null>(null)
  const [form, setForm] = useState<EmployeeForm>(defaultForm)
  const [formErrors, setFormErrors] = useState<Partial<EmployeeForm>>({})
  const [createdUsername, setCreatedUsername] = useState<string | null>(null)
  const [createdPassword, setCreatedPassword] = useState<string | null>(null)

  const [deleteTarget, setDeleteTarget] = useState<Employee | null>(null)

  const { data: empData, isLoading } = useQuery({
    queryKey: ['employees', page, search, filterDept, filterStatus],
    queryFn: () =>
      employeeApi.getAll({
        page,
        page_size: 20,
        search: search || undefined,
        department_id: filterDept ? Number(filterDept) : undefined,
        status: filterStatus || undefined,
      }),
  })

  const { data: deptData } = useQuery({
    queryKey: ['departments'],
    queryFn: departmentApi.getAll,
  })

  const createMutation = useMutation({
    mutationFn: employeeApi.create,
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['employees'] })
      if (res.data?.username) {
        setCreatedUsername(res.data.username)
        setCreatedPassword(res.data.temp_password || null)
      } else {
        closeModal()
      }
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<Employee> }) =>
      employeeApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['employees'] })
      closeModal()
    },
  })

  const deleteMutation = useMutation({
    mutationFn: employeeApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['employees'] })
      setDeleteTarget(null)
    },
  })

  const employees = empData?.data?.items || []
  const totalPages = empData?.data?.total_pages || 1
  const totalItems = empData?.data?.total || 0
  const departments: Department[] = deptData?.data || []

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    setSearch(searchInput)
    setPage(1)
  }

  const openCreate = () => {
    setEditEmployee(null)
    setForm(defaultForm)
    setFormErrors({})
    setCreatedUsername(null)
    setCreatedPassword(null)
    setShowModal(true)
  }

  const openEdit = (emp: Employee) => {
    setEditEmployee(emp)
    setForm({
      full_name: emp.full_name,
      email: emp.email,
      phone: emp.phone,
      position: emp.position,
      department_id: String(emp.department_id),
      password: '',
      role: emp.role || 'employee',
      status: emp.status,
    })
    setFormErrors({})
    setCreatedUsername(null)
    setCreatedPassword(null)
    setShowModal(true)
  }

  const closeModal = () => {
    setShowModal(false)
    setEditEmployee(null)
    setCreatedUsername(null)
    setCreatedPassword(null)
  }

  const validateForm = (): boolean => {
    const errors: Partial<EmployeeForm> = {}
    if (!form.full_name.trim()) errors.full_name = 'Bắt buộc'
    if (!form.email.trim()) errors.email = 'Bắt buộc'
    else if (!/\S+@\S+\.\S+/.test(form.email)) errors.email = 'Email không hợp lệ'
    if (!form.position.trim()) errors.position = 'Bắt buộc'
    if (!form.department_id) errors.department_id = 'Bắt buộc'
    setFormErrors(errors)
    return Object.keys(errors).length === 0
  }

  const handleSubmit = () => {
    if (!validateForm()) return
    const payload = {
      full_name: form.full_name,
      email: form.email,
      phone: form.phone,
      position: form.position,
      department_id: Number(form.department_id),
      status: form.status,
      role: form.role,
      ...(form.password.trim() ? { password: form.password } : {}),
    }
    if (editEmployee) {
      updateMutation.mutate({ id: editEmployee.id, data: payload })
    } else {
      createMutation.mutate(payload)
    }
  }

  const isMutating = createMutation.isPending || updateMutation.isPending

  return (
    <div>
      <PageTitle
        title="Quản lý Nhân viên"
        subtitle={`Tổng cộng ${totalItems} nhân viên`}
        actions={
          <button onClick={openCreate} className="btn-primary flex items-center gap-2">
            <Plus size={18} />
            Thêm nhân viên
          </button>
        }
      />

      {/* Filters */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4 mb-4">
        <div className="flex flex-col sm:flex-row gap-3">
          <form onSubmit={handleSearch} className="flex-1 flex gap-2">
            <div className="relative flex-1">
              <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <input
                type="text"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                placeholder="Tìm theo tên, mã nhân viên..."
                className="input-field pl-9"
              />
            </div>
            <button type="submit" className="btn-primary px-4">
              Tìm
            </button>
          </form>
          <select
            value={filterDept}
            onChange={(e) => { setFilterDept(e.target.value); setPage(1) }}
            className="input-field w-auto"
          >
            <option value="">Tất cả phòng ban</option>
            {departments.map((d) => (
              <option key={d.id} value={d.id}>{d.name}</option>
            ))}
          </select>
          <select
            value={filterStatus}
            onChange={(e) => { setFilterStatus(e.target.value); setPage(1) }}
            className="input-field w-auto"
          >
            <option value="">Tất cả trạng thái</option>
            <option value="active">Đang hoạt động</option>
            <option value="inactive">Không hoạt động</option>
          </select>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        {isLoading ? (
          <div className="flex justify-center py-16">
            <LoadingSpinner size="md" />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead>
                <tr>
                  <th className="table-header">Mã NV</th>
                  <th className="table-header">Họ tên</th>
                  <th className="table-header">Phòng ban</th>
                  <th className="table-header">Chức vụ</th>
                  <th className="table-header">Email</th>
                  <th className="table-header">Trạng thái</th>
                  <th className="table-header">Khuôn mặt</th>
                  <th className="table-header">RFID</th>
                  <th className="table-header text-right">Thao tác</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {employees.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="py-12 text-center text-gray-400 text-sm">
                      Không tìm thấy nhân viên nào
                    </td>
                  </tr>
                ) : (
                  employees.map((emp) => (
                    <tr key={emp.id} className="table-row">
                      <td className="table-cell font-mono text-xs text-gray-500">
                        {emp.employee_code}
                      </td>
                      <td className="table-cell font-medium">{emp.full_name}</td>
                      <td className="table-cell text-gray-500">{emp.department?.name || '—'}</td>
                      <td className="table-cell text-gray-500">{emp.position}</td>
                      <td className="table-cell text-gray-500">{emp.email}</td>
                      <td className="table-cell">
                        <StatusBadge status={emp.status} />
                      </td>
                      <td className="table-cell">
                        {emp.has_face ? (
                          <CheckCircle size={18} className="text-green-500" />
                        ) : (
                          <XCircle size={18} className="text-gray-300" />
                        )}
                      </td>
                      <td className="table-cell">
                        {emp.has_rfid ? (
                          <CheckCircle size={18} className="text-green-500" />
                        ) : (
                          <XCircle size={18} className="text-gray-300" />
                        )}
                      </td>
                      <td className="table-cell text-right">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => openEdit(emp)}
                            className="p-1.5 text-mint-600 hover:bg-mint-50 rounded-lg transition-colors"
                            title="Chỉnh sửa"
                          >
                            <Edit2 size={16} />
                          </button>
                          <button
                            onClick={() => setDeleteTarget(emp)}
                            className="p-1.5 text-red-500 hover:bg-red-50 rounded-lg transition-colors"
                            title="Xóa"
                          >
                            <Trash2 size={16} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
        <Pagination
          currentPage={page}
          totalPages={totalPages}
          onPageChange={setPage}
          totalItems={totalItems}
          pageSize={20}
        />
      </div>

      {/* Add/Edit Modal */}
      <Modal
        isOpen={showModal}
        onClose={closeModal}
        title={editEmployee ? 'Chỉnh sửa nhân viên' : 'Thêm nhân viên mới'}
        size="lg"
        footer={
          createdUsername ? (
            <button onClick={closeModal} className="btn-primary">
              Đóng
            </button>
          ) : (
            <>
              <button onClick={closeModal} className="btn-secondary">Hủy</button>
              <button onClick={handleSubmit} disabled={isMutating} className="btn-primary">
                {isMutating ? <LoadingSpinner size="sm" /> : editEmployee ? 'Lưu thay đổi' : 'Thêm mới'}
              </button>
            </>
          )
        }
      >
        {createdUsername ? (
          <div className="text-center py-4">
            <CheckCircle size={48} className="text-green-500 mx-auto mb-3" />
            <p className="text-lg font-semibold text-gray-800 mb-2">
              Thêm nhân viên thành công!
            </p>
            <p className="text-gray-500 mb-4">Thông tin tài khoản đăng nhập:</p>
            <div className="bg-mint-50 border border-mint-200 rounded-lg p-4 text-left space-y-2">
              <p className="text-sm text-gray-600">
                Tên đăng nhập:{' '}
                <span className="font-bold text-mint-700">{createdUsername}</span>
              </p>
              <p className="text-sm text-gray-600">
                Mật khẩu:{' '}
                <span className="font-bold text-mint-700">{createdPassword || '123456'}</span>
              </p>
              <p className="text-xs text-gray-400 pt-1">
                Lưu lại thông tin này và yêu cầu nhân viên đổi mật khẩu sau lần đăng nhập đầu tiên.
              </p>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Họ tên <span className="text-red-500">*</span>
              </label>
              <input
                className={`input-field ${formErrors.full_name ? 'border-red-400' : ''}`}
                value={form.full_name}
                onChange={(e) => setForm({ ...form, full_name: e.target.value })}
                placeholder="Nguyễn Văn A"
              />
              {formErrors.full_name && (
                <p className="text-red-500 text-xs mt-1">{formErrors.full_name}</p>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Email <span className="text-red-500">*</span>
              </label>
              <input
                type="email"
                className={`input-field ${formErrors.email ? 'border-red-400' : ''}`}
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                placeholder="example@company.com"
              />
              {formErrors.email && (
                <p className="text-red-500 text-xs mt-1">{formErrors.email}</p>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Số điện thoại
              </label>
              <input
                className="input-field"
                value={form.phone}
                onChange={(e) => setForm({ ...form, phone: e.target.value })}
                placeholder="0901234567"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Chức vụ <span className="text-red-500">*</span>
              </label>
              <input
                className={`input-field ${formErrors.position ? 'border-red-400' : ''}`}
                value={form.position}
                onChange={(e) => setForm({ ...form, position: e.target.value })}
                placeholder="Kỹ sư phần mềm"
              />
              {formErrors.position && (
                <p className="text-red-500 text-xs mt-1">{formErrors.position}</p>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Phòng ban <span className="text-red-500">*</span>
              </label>
              <select
                className={`input-field ${formErrors.department_id ? 'border-red-400' : ''}`}
                value={form.department_id}
                onChange={(e) => setForm({ ...form, department_id: e.target.value })}
              >
                <option value="">-- Chọn phòng ban --</option>
                {departments.map((d) => (
                  <option key={d.id} value={d.id}>{d.name}</option>
                ))}
              </select>
              {formErrors.department_id && (
                <p className="text-red-500 text-xs mt-1">{formErrors.department_id}</p>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Trạng thái
              </label>
              <select
                className="input-field"
                value={form.status}
                onChange={(e) => setForm({ ...form, status: e.target.value as 'active' | 'inactive' })}
              >
                <option value="active">Đang hoạt động</option>
                <option value="inactive">Không hoạt động</option>
              </select>
            </div>

            {/* Tài khoản đăng nhập — luôn tự động theo mã NV */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Tài khoản đăng nhập
              </label>
              <div className="input-field bg-gray-50 text-gray-500 select-none cursor-default">
                {editEmployee
                  ? (editEmployee.username || '—')
                  : 'Tự động theo mã nhân viên (emp001...)'}
              </div>
              {editEmployee && (
                <p className="text-gray-400 text-xs mt-1">Tài khoản = mã nhân viên, không thể thay đổi</p>
              )}
            </div>

            {/* Quyền hệ thống */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Quyền hệ thống
              </label>
              <select
                className="input-field"
                value={form.role}
                onChange={(e) => setForm({ ...form, role: e.target.value as 'admin' | 'employee' })}
              >
                <option value="employee">Nhân viên</option>
                <option value="admin">Quản lý (Admin)</option>
              </select>
            </div>

            {!editEmployee && (
              <div className="sm:col-span-2">
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Mật khẩu ban đầu
                </label>
                <input
                  type="password"
                  className="input-field"
                  value={form.password}
                  onChange={(e) => setForm({ ...form, password: e.target.value })}
                  placeholder="Để trống → mặc định 123456"
                />
                <p className="text-gray-400 text-xs mt-1">
                  Nhân viên cần đổi mật khẩu sau lần đăng nhập đầu tiên
                </p>
              </div>
            )}

            {(createMutation.isError || updateMutation.isError) && (
              <div className="sm:col-span-2 bg-red-50 border border-red-200 rounded-lg p-3">
                <p className="text-red-700 text-sm">
                  {createMutation.error?.message || updateMutation.error?.message || 'Có lỗi xảy ra'}
                </p>
              </div>
            )}
          </div>
        )}
      </Modal>

      {/* Delete Confirm Modal */}
      <Modal
        isOpen={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        title="Xác nhận xóa"
        size="sm"
        footer={
          <>
            <button onClick={() => setDeleteTarget(null)} className="btn-secondary">
              Hủy
            </button>
            <button
              onClick={() => deleteTarget && deleteMutation.mutate(deleteTarget.id)}
              disabled={deleteMutation.isPending}
              className="btn-danger"
            >
              {deleteMutation.isPending ? <LoadingSpinner size="sm" /> : 'Xóa'}
            </button>
          </>
        }
      >
        <p className="text-gray-600">
          Bạn có chắc chắn muốn xóa nhân viên{' '}
          <span className="font-semibold text-gray-900">{deleteTarget?.full_name}</span> không?
        </p>
        <p className="text-gray-500 text-sm mt-2">Thao tác này không thể hoàn tác.</p>
      </Modal>
    </div>
  )
}

export default Employees

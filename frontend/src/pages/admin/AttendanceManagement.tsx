import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Edit2, Trash2, Search } from 'lucide-react'
import { attendanceApi, employeeApi } from '../../services/api'
import type { AttendanceLog, Employee } from '../../types'
import PageTitle from '../../components/PageTitle'
import Modal from '../../components/Modal'
import StatusBadge from '../../components/StatusBadge'
import LoadingSpinner from '../../components/LoadingSpinner'
import Pagination from '../../components/Pagination'
import { format } from 'date-fns'

interface AttendanceForm {
  employee_id: string
  date: string
  check_in: string
  check_out: string
  note: string
}

const defaultForm: AttendanceForm = {
  employee_id: '',
  date: format(new Date(), 'yyyy-MM-dd'),
  check_in: '08:00',
  check_out: '17:00',
  note: '',
}

const AttendanceManagement: React.FC = () => {
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [dateFilter, setDateFilter] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')

  const [showModal, setShowModal] = useState(false)
  const [editLog, setEditLog] = useState<AttendanceLog | null>(null)
  const [form, setForm] = useState<AttendanceForm>(defaultForm)
  const [formErrors, setFormErrors] = useState<Partial<AttendanceForm>>({})
  const [deleteTarget, setDeleteTarget] = useState<AttendanceLog | null>(null)

  const { data: logsData, isLoading } = useQuery({
    queryKey: ['attendance', page, dateFilter, search],
    queryFn: () =>
      attendanceApi.getLogs({
        page,
        page_size: 20,
        date: dateFilter || undefined,
        search: search || undefined,
      }),
  })

  const { data: empData } = useQuery({
    queryKey: ['employees-all'],
    queryFn: () => employeeApi.getAll({ page: 1, page_size: 200 }),
  })

  const createMutation = useMutation({
    mutationFn: attendanceApi.createManual,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['attendance'] })
      closeModal()
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<AttendanceLog> }) =>
      attendanceApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['attendance'] })
      closeModal()
    },
  })

  const deleteMutation = useMutation({
    mutationFn: attendanceApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['attendance'] })
      setDeleteTarget(null)
    },
  })

  const logs: AttendanceLog[] = logsData?.data?.items || []
  const totalPages = logsData?.data?.total_pages || 1
  const totalItems = logsData?.data?.total || 0
  const employees: Employee[] = empData?.data?.items || []

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    setSearch(searchInput)
    setPage(1)
  }

  const openCreate = () => {
    setEditLog(null)
    setForm(defaultForm)
    setFormErrors({})
    setShowModal(true)
  }

  const openEdit = (log: AttendanceLog) => {
    setEditLog(log)
    setForm({
      employee_id: String(log.employee_id),
      date: log.date,
      check_in: log.check_in ? format(new Date(log.check_in), 'HH:mm') : '',
      check_out: log.check_out ? format(new Date(log.check_out), 'HH:mm') : '',
      note: log.note || '',
    })
    setFormErrors({})
    setShowModal(true)
  }

  const closeModal = () => {
    setShowModal(false)
    setEditLog(null)
  }

  const validate = (): boolean => {
    const errors: Partial<AttendanceForm> = {}
    if (!form.employee_id) errors.employee_id = 'Bắt buộc'
    if (!form.date) errors.date = 'Bắt buộc'
    if (!form.check_in) errors.check_in = 'Bắt buộc'
    setFormErrors(errors)
    return Object.keys(errors).length === 0
  }

  const handleSubmit = () => {
    if (!validate()) return
    const payload = {
      employee_id: Number(form.employee_id),
      date: form.date,
      check_in: `${form.date}T${form.check_in}:00`,
      check_out: form.check_out ? `${form.date}T${form.check_out}:00` : undefined,
      note: form.note || undefined,
    }
    if (editLog) {
      updateMutation.mutate({ id: editLog.id, data: payload })
    } else {
      createMutation.mutate(payload)
    }
  }

  const isMutating = createMutation.isPending || updateMutation.isPending

  return (
    <div>
      <PageTitle
        title="Quản lý Chấm công"
        subtitle={`${totalItems} bản ghi`}
        actions={
          <button onClick={openCreate} className="btn-primary flex items-center gap-2">
            <Plus size={18} />
            Thêm thủ công
          </button>
        }
      />

      {/* Filters */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4 mb-4">
        <div className="flex flex-col sm:flex-row gap-3">
          <form onSubmit={handleSearch} className="flex gap-2 flex-1">
            <div className="relative flex-1">
              <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <input
                type="text"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                placeholder="Tìm kiếm nhân viên..."
                className="input-field pl-9"
              />
            </div>
            <button type="submit" className="btn-primary px-4">Tìm</button>
          </form>
          <input
            type="date"
            value={dateFilter}
            onChange={(e) => { setDateFilter(e.target.value); setPage(1) }}
            className="input-field w-auto"
          />
          {dateFilter && (
            <button
              onClick={() => { setDateFilter(''); setPage(1) }}
              className="btn-secondary text-sm"
            >
              Xóa lọc
            </button>
          )}
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
                  <th className="table-header">Nhân viên</th>
                  <th className="table-header">Ngày</th>
                  <th className="table-header">Giờ vào</th>
                  <th className="table-header">Giờ ra</th>
                  <th className="table-header">Phương thức</th>
                  <th className="table-header">Số giờ</th>
                  <th className="table-header">Ghi chú</th>
                  <th className="table-header text-right">Thao tác</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {logs.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="py-12 text-center text-gray-400 text-sm">
                      Không có dữ liệu chấm công
                    </td>
                  </tr>
                ) : (
                  logs.map((log) => (
                    <tr key={log.id} className="table-row">
                      <td className="table-cell font-medium">
                        {log.employee?.full_name || `NV#${log.employee_id}`}
                      </td>
                      <td className="table-cell text-gray-500">
                        {format(new Date(log.date), 'dd/MM/yyyy')}
                      </td>
                      <td className="table-cell text-gray-700">
                        {log.check_in ? format(new Date(log.check_in), 'HH:mm') : '—'}
                      </td>
                      <td className="table-cell text-gray-700">
                        {log.check_out ? format(new Date(log.check_out), 'HH:mm') : '—'}
                      </td>
                      <td className="table-cell">
                        <StatusBadge status={log.method} />
                      </td>
                      <td className="table-cell">
                        {log.work_hours != null ? (
                          <span className="font-medium">{log.work_hours.toFixed(1)}h</span>
                        ) : (
                          '—'
                        )}
                      </td>
                      <td className="table-cell text-gray-500 max-w-xs truncate">
                        {log.note || '—'}
                      </td>
                      <td className="table-cell text-right">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => openEdit(log)}
                            className="p-1.5 text-mint-600 hover:bg-mint-50 rounded-lg"
                          >
                            <Edit2 size={15} />
                          </button>
                          <button
                            onClick={() => setDeleteTarget(log)}
                            className="p-1.5 text-red-500 hover:bg-red-50 rounded-lg"
                          >
                            <Trash2 size={15} />
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
        title={editLog ? 'Chỉnh sửa chấm công' : 'Thêm chấm công thủ công'}
        size="md"
        footer={
          <>
            <button onClick={closeModal} className="btn-secondary">Hủy</button>
            <button onClick={handleSubmit} disabled={isMutating} className="btn-primary">
              {isMutating ? <LoadingSpinner size="sm" /> : editLog ? 'Lưu' : 'Thêm'}
            </button>
          </>
        }
      >
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="sm:col-span-2">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Nhân viên <span className="text-red-500">*</span>
            </label>
            <select
              className={`input-field ${formErrors.employee_id ? 'border-red-400' : ''}`}
              value={form.employee_id}
              onChange={(e) => setForm({ ...form, employee_id: e.target.value })}
            >
              <option value="">-- Chọn nhân viên --</option>
              {employees.map((emp) => (
                <option key={emp.id} value={emp.id}>
                  {emp.full_name} ({emp.employee_code})
                </option>
              ))}
            </select>
            {formErrors.employee_id && (
              <p className="text-red-500 text-xs mt-1">{formErrors.employee_id}</p>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Ngày <span className="text-red-500">*</span>
            </label>
            <input
              type="date"
              className={`input-field ${formErrors.date ? 'border-red-400' : ''}`}
              value={form.date}
              onChange={(e) => setForm({ ...form, date: e.target.value })}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Giờ vào <span className="text-red-500">*</span>
            </label>
            <input
              type="time"
              className={`input-field ${formErrors.check_in ? 'border-red-400' : ''}`}
              value={form.check_in}
              onChange={(e) => setForm({ ...form, check_in: e.target.value })}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Giờ ra</label>
            <input
              type="time"
              className="input-field"
              value={form.check_out}
              onChange={(e) => setForm({ ...form, check_out: e.target.value })}
            />
          </div>

          <div className="sm:col-span-2">
            <label className="block text-sm font-medium text-gray-700 mb-1">Ghi chú</label>
            <textarea
              className="input-field resize-none h-20"
              value={form.note}
              onChange={(e) => setForm({ ...form, note: e.target.value })}
              placeholder="Nhập ghi chú (nếu có)"
            />
          </div>

          {(createMutation.isError || updateMutation.isError) && (
            <div className="sm:col-span-2 bg-red-50 border border-red-200 rounded-lg p-3">
              <p className="text-red-700 text-sm">
                {createMutation.error?.message || updateMutation.error?.message || 'Có lỗi xảy ra'}
              </p>
            </div>
          )}
        </div>
      </Modal>

      {/* Delete Confirm */}
      <Modal
        isOpen={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        title="Xóa bản ghi chấm công"
        size="sm"
        footer={
          <>
            <button onClick={() => setDeleteTarget(null)} className="btn-secondary">Hủy</button>
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
          Xóa bản ghi chấm công của{' '}
          <strong>{deleteTarget?.employee?.full_name || `NV#${deleteTarget?.employee_id}`}</strong> ngày{' '}
          {deleteTarget ? format(new Date(deleteTarget.date), 'dd/MM/yyyy') : ''}?
        </p>
      </Modal>
    </div>
  )
}

export default AttendanceManagement

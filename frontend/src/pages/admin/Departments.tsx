import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Edit2, Trash2, Building2, AlertTriangle } from 'lucide-react'
import { departmentApi } from '../../services/api'
import type { Department } from '../../types'
import PageTitle from '../../components/PageTitle'
import Modal from '../../components/Modal'
import LoadingSpinner from '../../components/LoadingSpinner'
import { format } from 'date-fns'

const Departments: React.FC = () => {
  const queryClient = useQueryClient()
  const [showModal, setShowModal] = useState(false)
  const [editDept, setEditDept] = useState<Department | null>(null)
  const [name, setName] = useState('')
  const [nameError, setNameError] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<Department | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['departments'],
    queryFn: departmentApi.getAll,
  })

  const createMutation = useMutation({
    mutationFn: departmentApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['departments'] })
      closeModal()
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, name }: { id: number; name: string }) =>
      departmentApi.update(id, { name }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['departments'] })
      closeModal()
    },
  })

  const deleteMutation = useMutation({
    mutationFn: departmentApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['departments'] })
      setDeleteTarget(null)
    },
  })

  const departments: Department[] = data?.data || []

  const openCreate = () => {
    setEditDept(null)
    setName('')
    setNameError('')
    setShowModal(true)
  }

  const openEdit = (dept: Department) => {
    setEditDept(dept)
    setName(dept.name)
    setNameError('')
    setShowModal(true)
  }

  const closeModal = () => {
    setShowModal(false)
    setEditDept(null)
  }

  const handleSubmit = () => {
    if (!name.trim()) {
      setNameError('Tên phòng ban không được để trống')
      return
    }
    setNameError('')
    if (editDept) {
      updateMutation.mutate({ id: editDept.id, name: name.trim() })
    } else {
      createMutation.mutate({ name: name.trim() })
    }
  }

  const isMutating = createMutation.isPending || updateMutation.isPending

  return (
    <div>
      <PageTitle
        title="Quản lý Phòng ban"
        subtitle={`${departments.length} phòng ban`}
        actions={
          <button onClick={openCreate} className="btn-primary flex items-center gap-2">
            <Plus size={18} />
            Thêm phòng ban
          </button>
        }
      />

      {isLoading ? (
        <div className="flex justify-center py-16">
          <LoadingSpinner size="md" />
        </div>
      ) : (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200">
            <thead>
              <tr>
                <th className="table-header">#</th>
                <th className="table-header">Tên phòng ban</th>
                <th className="table-header">Số nhân viên</th>
                <th className="table-header">Ngày tạo</th>
                <th className="table-header text-right">Thao tác</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {departments.length === 0 ? (
                <tr>
                  <td colSpan={5} className="py-16 text-center text-gray-400 text-sm">
                    Chưa có phòng ban nào
                  </td>
                </tr>
              ) : (
                departments.map((dept, idx) => (
                  <tr key={dept.id} className="table-row">
                    <td className="table-cell text-gray-400">{idx + 1}</td>
                    <td className="table-cell">
                      <div className="flex items-center gap-2">
                        <div className="w-8 h-8 bg-mint-100 rounded-lg flex items-center justify-center">
                          <Building2 size={15} className="text-mint-600" />
                        </div>
                        <span className="font-medium">{dept.name}</span>
                      </div>
                    </td>
                    <td className="table-cell">
                      <span className="inline-flex items-center justify-center w-8 h-8 bg-gray-100 rounded-full text-sm font-medium text-gray-700">
                        {dept.employee_count}
                      </span>
                    </td>
                    <td className="table-cell text-gray-500">
                      {dept.created_at
                        ? format(new Date(dept.created_at), 'dd/MM/yyyy')
                        : '—'}
                    </td>
                    <td className="table-cell text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => openEdit(dept)}
                          className="p-1.5 text-mint-600 hover:bg-mint-50 rounded-lg transition-colors"
                          title="Chỉnh sửa"
                        >
                          <Edit2 size={16} />
                        </button>
                        <button
                          onClick={() => setDeleteTarget(dept)}
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

      {/* Add/Edit Modal */}
      <Modal
        isOpen={showModal}
        onClose={closeModal}
        title={editDept ? 'Chỉnh sửa phòng ban' : 'Thêm phòng ban mới'}
        size="sm"
        footer={
          <>
            <button onClick={closeModal} className="btn-secondary">Hủy</button>
            <button onClick={handleSubmit} disabled={isMutating} className="btn-primary">
              {isMutating ? <LoadingSpinner size="sm" /> : editDept ? 'Lưu' : 'Thêm mới'}
            </button>
          </>
        }
      >
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1.5">
            Tên phòng ban <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            className={`input-field ${nameError ? 'border-red-400' : ''}`}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="VD: Phòng Kỹ thuật"
            onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
            autoFocus
          />
          {nameError && <p className="text-red-500 text-xs mt-1">{nameError}</p>}
          {(createMutation.isError || updateMutation.isError) && (
            <p className="text-red-500 text-xs mt-2">
              {createMutation.error?.message || updateMutation.error?.message || 'Có lỗi xảy ra'}
            </p>
          )}
        </div>
      </Modal>

      {/* Delete Modal */}
      <Modal
        isOpen={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        title="Xác nhận xóa phòng ban"
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
        <div className="space-y-3">
          <p className="text-gray-600">
            Bạn có chắc chắn muốn xóa phòng ban{' '}
            <span className="font-semibold">{deleteTarget?.name}</span>?
          </p>
          {deleteTarget && deleteTarget.employee_count > 0 && (
            <div className="flex items-start gap-2 bg-yellow-50 border border-yellow-200 rounded-lg p-3">
              <AlertTriangle size={16} className="text-yellow-600 flex-shrink-0 mt-0.5" />
              <p className="text-yellow-700 text-sm">
                Phòng ban này có <strong>{deleteTarget.employee_count}</strong> nhân viên.
                Hãy chuyển nhân viên sang phòng ban khác trước khi xóa.
              </p>
            </div>
          )}
        </div>
      </Modal>
    </div>
  )
}

export default Departments

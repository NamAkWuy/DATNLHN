import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, ToggleLeft, ToggleRight, UserCheck } from 'lucide-react'
import { rfidApi, employeeApi } from '../../services/api'
import type { RFIDCard, Employee } from '../../types'
import PageTitle from '../../components/PageTitle'
import Modal from '../../components/Modal'
import StatusBadge from '../../components/StatusBadge'
import LoadingSpinner from '../../components/LoadingSpinner'
import { format } from 'date-fns'

const RFIDManagement: React.FC = () => {
  const queryClient = useQueryClient()

  const [showAddModal, setShowAddModal] = useState(false)
  const [showAssignModal, setShowAssignModal] = useState(false)
  const [assignTarget, setAssignTarget] = useState<RFIDCard | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<RFIDCard | null>(null)

  const [uid, setUid] = useState('')
  const [selectedEmployee, setSelectedEmployee] = useState('')
  const [uidError, setUidError] = useState('')
  const [assignEmployee, setAssignEmployee] = useState('')

  const { data: rfidData, isLoading } = useQuery({
    queryKey: ['rfid'],
    queryFn: rfidApi.getAll,
  })

  const { data: empData } = useQuery({
    queryKey: ['employees-all'],
    queryFn: () => employeeApi.getAll({ page: 1, page_size: 200 }),
  })

  const createMutation = useMutation({
    mutationFn: rfidApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rfid'] })
      queryClient.invalidateQueries({ queryKey: ['employees'] })
      setShowAddModal(false)
      setUid('')
      setSelectedEmployee('')
    },
  })

  const assignMutation = useMutation({
    mutationFn: ({ id, employee_id }: { id: number; employee_id: number }) =>
      rfidApi.assign(id, employee_id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rfid'] })
      queryClient.invalidateQueries({ queryKey: ['employees'] })
      setShowAssignModal(false)
      setAssignTarget(null)
      setAssignEmployee('')
    },
  })

  const toggleMutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: 'active' | 'disabled' }) =>
      rfidApi.updateStatus(id, status),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['rfid'] }),
  })

  const deleteMutation = useMutation({
    mutationFn: rfidApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rfid'] })
      queryClient.invalidateQueries({ queryKey: ['employees'] })
      setDeleteTarget(null)
    },
  })

  const cards: RFIDCard[] = rfidData?.data || []
  const employees: Employee[] = empData?.data?.items || []

  // Bản đồ employee_id → UID thẻ đang hoạt động (để chặn gán trùng thẻ cho 1 nhân viên)
  const activeCardByEmployee = new Map<number, string>()
  for (const c of cards) {
    if (c.employee_id && c.status === 'active') {
      activeCardByEmployee.set(c.employee_id, c.uid)
    }
  }

  const handleAdd = () => {
    if (!uid.trim()) {
      setUidError('Vui lòng nhập mã UID')
      return
    }
    setUidError('')
    createMutation.mutate({
      uid: uid.trim(),
      employee_id: selectedEmployee ? Number(selectedEmployee) : undefined,
    })
  }

  const openAssign = (card: RFIDCard) => {
    setAssignTarget(card)
    setAssignEmployee(card.employee_id ? String(card.employee_id) : '')
    assignMutation.reset()
    setShowAssignModal(true)
  }

  const handleAssign = () => {
    if (assignTarget && assignEmployee) {
      assignMutation.mutate({ id: assignTarget.id, employee_id: Number(assignEmployee) })
    }
  }

  return (
    <div>
      <PageTitle
        title="Quản lý Thẻ RFID"
        subtitle={`${cards.length} thẻ RFID`}
        actions={
          <button onClick={() => setShowAddModal(true)} className="btn-primary flex items-center gap-2">
            <Plus size={18} />
            Thêm thẻ RFID
          </button>
        }
      />

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
                  <th className="table-header">Mã UID</th>
                  <th className="table-header">Nhân viên</th>
                  <th className="table-header">Trạng thái</th>
                  <th className="table-header">Ngày gán</th>
                  <th className="table-header text-right">Thao tác</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {cards.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="py-12 text-center text-gray-400 text-sm">
                      Chưa có thẻ RFID nào
                    </td>
                  </tr>
                ) : (
                  cards.map((card) => (
                    <tr key={card.id} className="table-row">
                      <td className="table-cell font-mono font-medium text-mint-700">
                        {card.uid}
                      </td>
                      <td className="table-cell">
                        {card.employee ? (
                          <div>
                            <span className="font-medium">{card.employee.full_name}</span>
                            <span className="text-xs text-gray-400 ml-1">({card.employee.employee_code})</span>
                          </div>
                        ) : (
                          <span className="text-gray-400 italic text-sm">Chưa gán</span>
                        )}
                      </td>
                      <td className="table-cell">
                        <StatusBadge status={card.status} />
                      </td>
                      <td className="table-cell text-gray-500">
                        {card.assigned_at
                          ? format(new Date(card.assigned_at), 'dd/MM/yyyy HH:mm')
                          : '—'}
                      </td>
                      <td className="table-cell text-right">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => openAssign(card)}
                            className="p-1.5 text-mint-600 hover:bg-mint-50 rounded-lg transition-colors"
                            title="Gán nhân viên"
                          >
                            <UserCheck size={16} />
                          </button>
                          <button
                            onClick={() => toggleMutation.mutate({
                              id: card.id,
                              status: card.status === 'active' ? 'disabled' : 'active'
                            })}
                            disabled={toggleMutation.isPending}
                            className={`p-1.5 rounded-lg transition-colors ${
                              card.status === 'active'
                                ? 'text-green-600 hover:bg-green-50'
                                : 'text-gray-400 hover:bg-gray-100'
                            }`}
                            title={card.status === 'active' ? 'Vô hiệu hóa' : 'Kích hoạt'}
                          >
                            {card.status === 'active' ? (
                              <ToggleRight size={20} />
                            ) : (
                              <ToggleLeft size={20} />
                            )}
                          </button>
                          <button
                            onClick={() => setDeleteTarget(card)}
                            className="p-1.5 text-red-500 hover:bg-red-50 rounded-lg transition-colors"
                            title="Xóa thẻ"
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
      </div>

      {/* Add Card Modal */}
      <Modal
        isOpen={showAddModal}
        onClose={() => { setShowAddModal(false); setUid(''); setSelectedEmployee(''); setUidError('') }}
        title="Thêm thẻ RFID mới"
        size="sm"
        footer={
          <>
            <button onClick={() => setShowAddModal(false)} className="btn-secondary">Hủy</button>
            <button onClick={handleAdd} disabled={createMutation.isPending} className="btn-primary">
              {createMutation.isPending ? <LoadingSpinner size="sm" /> : 'Thêm thẻ'}
            </button>
          </>
        }
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">
              Mã UID <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              className={`input-field font-mono ${uidError ? 'border-red-400' : ''}`}
              value={uid}
              onChange={(e) => setUid(e.target.value.toUpperCase())}
              placeholder="VD: A1B2C3D4"
            />
            {uidError && <p className="text-red-500 text-xs mt-1">{uidError}</p>}
            <p className="text-gray-400 text-xs mt-1">
              Nhập mã UID từ thẻ RFID (hoặc để thiết bị đọc tự điền)
            </p>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">
              Gán cho nhân viên (tùy chọn)
            </label>
            <select
              className="input-field"
              value={selectedEmployee}
              onChange={(e) => { setSelectedEmployee(e.target.value); createMutation.reset() }}
            >
              <option value="">-- Chọn nhân viên --</option>
              {employees.map((emp) => {
                const existingUid = activeCardByEmployee.get(emp.id)
                return (
                  <option key={emp.id} value={emp.id} disabled={!!existingUid}>
                    {emp.full_name} ({emp.employee_code}){existingUid ? ` — đã có thẻ ${existingUid}` : ''}
                  </option>
                )
              })}
            </select>
            {selectedEmployee && activeCardByEmployee.get(Number(selectedEmployee)) && (
              <p className="text-orange-600 text-xs mt-1">
                ⚠️ Nhân viên này đã có thẻ đang hoạt động. Vui lòng xóa hoặc vô hiệu hóa thẻ cũ trước.
              </p>
            )}
          </div>
          {createMutation.isError && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-700">
              {createMutation.error?.message || 'Có lỗi xảy ra'}
            </div>
          )}
        </div>
      </Modal>

      {/* Assign Modal */}
      <Modal
        isOpen={showAssignModal}
        onClose={() => { setShowAssignModal(false); assignMutation.reset() }}
        title={`Gán thẻ ${assignTarget?.uid}`}
        size="sm"
        footer={
          <>
            <button onClick={() => { setShowAssignModal(false); assignMutation.reset() }} className="btn-secondary">Hủy</button>
            <button
              onClick={handleAssign}
              disabled={!assignEmployee || assignMutation.isPending}
              className="btn-primary"
            >
              {assignMutation.isPending ? <LoadingSpinner size="sm" /> : 'Gán thẻ'}
            </button>
          </>
        }
      >
        <div className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">
              Chọn nhân viên <span className="text-red-500">*</span>
            </label>
            <select
              className="input-field"
              value={assignEmployee}
              onChange={(e) => { setAssignEmployee(e.target.value); assignMutation.reset() }}
            >
              <option value="">-- Chọn nhân viên --</option>
              {employees.map((emp) => {
                const existingUid = activeCardByEmployee.get(emp.id)
                const isCurrentCard = assignTarget?.employee_id === emp.id
                const hasOtherCard = existingUid && !isCurrentCard
                return (
                  <option key={emp.id} value={emp.id} disabled={!!hasOtherCard}>
                    {emp.full_name} ({emp.employee_code}){hasOtherCard ? ` — đã có thẻ ${existingUid}` : ''}
                  </option>
                )
              })}
            </select>
          </div>

          {/* Warning: selected employee already has an active card */}
          {assignEmployee && (() => {
            const empId = Number(assignEmployee)
            const existingUid = activeCardByEmployee.get(empId)
            const isCurrentCard = assignTarget?.employee_id === empId
            if (existingUid && !isCurrentCard) {
              return (
                <div className="bg-orange-50 border border-orange-200 rounded-lg p-3 text-sm text-orange-700">
                  ⚠️ Nhân viên này đã có thẻ <span className="font-mono font-semibold">{existingUid}</span> đang hoạt động.
                  Vui lòng xóa hoặc vô hiệu hóa thẻ cũ trước khi gán thẻ mới.
                </div>
              )
            }
            return null
          })()}

          {assignMutation.isError && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-700">
              {assignMutation.error?.message || 'Có lỗi xảy ra'}
            </div>
          )}
        </div>
      </Modal>

      {/* Delete Confirm */}
      <Modal
        isOpen={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        title="Xóa thẻ RFID"
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
          Bạn có chắc chắn muốn xóa thẻ RFID{' '}
          <span className="font-mono font-semibold">{deleteTarget?.uid}</span>?
        </p>
      </Modal>
    </div>
  )
}

export default RFIDManagement

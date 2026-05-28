import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Edit2, XCircle } from 'lucide-react'
import { leaveApi } from '../../services/api'
import type { LeaveRequest } from '../../types'
import PageTitle from '../../components/PageTitle'
import Modal from '../../components/Modal'
import StatusBadge from '../../components/StatusBadge'
import LoadingSpinner from '../../components/LoadingSpinner'
import Pagination from '../../components/Pagination'
import { format } from 'date-fns'

type TabKey = 'all' | 'cho_duyet' | 'da_duyet' | 'tu_choi' | 'da_huy'

const tabs: { key: TabKey; label: string }[] = [
  { key: 'all', label: 'Tất cả' },
  { key: 'cho_duyet', label: 'Chờ duyệt' },
  { key: 'da_duyet', label: 'Đã duyệt' },
  { key: 'tu_choi', label: 'Từ chối' },
  { key: 'da_huy', label: 'Đã hủy' },
]

const typeOptions = [
  { value: 'nghi_phep', label: 'Nghỉ phép' },
  { value: 'di_muon', label: 'Đi muộn' },
  { value: 've_som', label: 'Về sớm' },
]

const typeLabel: Record<string, string> = {
  nghi_phep: 'Nghỉ phép',
  di_muon: 'Đi muộn',
  ve_som: 'Về sớm',
}

interface RequestForm {
  type: 'nghi_phep' | 'di_muon' | 've_som'
  start_datetime: string
  end_datetime: string
  reason: string
}

const defaultForm: RequestForm = {
  type: 'nghi_phep',
  start_datetime: '',
  end_datetime: '',
  reason: '',
}

const MyRequests: React.FC = () => {
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useState<TabKey>('all')
  const [page, setPage] = useState(1)
  const [showModal, setShowModal] = useState(false)
  const [editRequest, setEditRequest] = useState<LeaveRequest | null>(null)
  const [form, setForm] = useState<RequestForm>(defaultForm)
  const [formErrors, setFormErrors] = useState<Partial<RequestForm>>({})
  const [cancelTarget, setCancelTarget] = useState<LeaveRequest | null>(null)

  const statusParam = activeTab === 'all' ? undefined : activeTab

  const { data, isLoading } = useQuery({
    queryKey: ['my-requests', activeTab, page],
    queryFn: () => leaveApi.getMyRequests({ status: statusParam, page, page_size: 15 }),
  })

  const createMutation = useMutation({
    mutationFn: leaveApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['my-requests'] })
      closeModal()
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<LeaveRequest> }) =>
      leaveApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['my-requests'] })
      closeModal()
    },
  })

  const cancelMutation = useMutation({
    mutationFn: leaveApi.cancel,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['my-requests'] })
      queryClient.invalidateQueries({ queryKey: ['my-requests-pending'] })
      setActiveTab('da_huy')
      setPage(1)
      setCancelTarget(null)
    },
  })

  const requests: LeaveRequest[] = data?.data?.items || []
  const totalPages = data?.data?.total_pages || 1
  const totalItems = data?.data?.total || 0

  const openCreate = () => {
    setEditRequest(null)
    setForm(defaultForm)
    setFormErrors({})
    setShowModal(true)
  }

  const openEdit = (req: LeaveRequest) => {
    setEditRequest(req)
    setForm({
      type: req.type,
      start_datetime: req.start_datetime.slice(0, 16),
      end_datetime: req.end_datetime.slice(0, 16),
      reason: req.reason,
    })
    setFormErrors({})
    setShowModal(true)
  }

  const closeModal = () => {
    setShowModal(false)
    setEditRequest(null)
    createMutation.reset()
    updateMutation.reset()
  }

  const openCancel = (req: LeaveRequest) => {
    cancelMutation.reset()
    setCancelTarget(req)
  }

  const closeCancel = () => {
    cancelMutation.reset()
    setCancelTarget(null)
  }

  const validate = (): boolean => {
    const errors: Partial<RequestForm> = {}
    if (!form.start_datetime) errors.start_datetime = 'Bắt buộc'
    if (!form.end_datetime) errors.end_datetime = 'Bắt buộc'
    if (!form.reason.trim()) errors.reason = 'Bắt buộc'
    if (form.start_datetime && form.end_datetime && form.start_datetime >= form.end_datetime) {
      errors.end_datetime = 'Thời gian kết thúc phải sau thời gian bắt đầu'
    }
    setFormErrors(errors)
    return Object.keys(errors).length === 0
  }

  const handleSubmit = () => {
    if (!validate()) return
    if (editRequest) {
      updateMutation.mutate({ id: editRequest.id, data: form })
    } else {
      createMutation.mutate(form)
    }
  }

  const isMutating = createMutation.isPending || updateMutation.isPending

  const formatDT = (dt: string) => {
    try { return format(new Date(dt), 'dd/MM/yyyy HH:mm') } catch { return dt }
  }

  return (
    <div>
      <PageTitle
        title="Đơn từ của tôi"
        actions={
          <button onClick={openCreate} className="btn-primary flex items-center gap-2">
            <Plus size={18} />
            Tạo đơn mới
          </button>
        }
      />

      {/* Tabs */}
      <div className="flex gap-1 bg-gray-100 p-1 rounded-xl mb-4 w-fit flex-wrap">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => { setActiveTab(tab.key); setPage(1) }}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
              activeTab === tab.key
                ? 'bg-white text-mint-600 shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

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
                  <th className="table-header">Loại đơn</th>
                  <th className="table-header">Từ</th>
                  <th className="table-header">Đến</th>
                  <th className="table-header">Lý do</th>
                  <th className="table-header">Ngày gửi</th>
                  <th className="table-header">Trạng thái</th>
                  <th className="table-header text-right">Thao tác</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {requests.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="py-12 text-center text-gray-400 text-sm">
                      Không có đơn nào
                    </td>
                  </tr>
                ) : (
                  requests.map((req) => (
                    <tr key={req.id} className="table-row">
                      <td className="table-cell">
                        <StatusBadge status={req.type} label={typeLabel[req.type]} />
                      </td>
                      <td className="table-cell text-sm text-gray-500">{formatDT(req.start_datetime)}</td>
                      <td className="table-cell text-sm text-gray-500">{formatDT(req.end_datetime)}</td>
                      <td className="table-cell max-w-xs">
                        <p className="truncate text-sm text-gray-600">{req.reason}</p>
                      </td>
                      <td className="table-cell text-sm text-gray-500">{formatDT(req.created_at)}</td>
                      <td className="table-cell">
                        <StatusBadge status={req.status} />
                      </td>
                      <td className="table-cell text-right">
                        {req.status === 'cho_duyet' && (
                          <div className="flex items-center justify-end gap-2">
                            <button
                              onClick={() => openEdit(req)}
                              className="p-1.5 text-mint-600 hover:bg-mint-50 rounded-lg transition-colors"
                              title="Chỉnh sửa"
                            >
                              <Edit2 size={15} />
                            </button>
                            <button
                              onClick={() => openCancel(req)}
                              className="p-1.5 text-red-500 hover:bg-red-50 rounded-lg transition-colors"
                              title="Hủy đơn"
                            >
                              <XCircle size={15} />
                            </button>
                          </div>
                        )}
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
          pageSize={15}
        />
      </div>

      {/* Create/Edit Modal */}
      <Modal
        isOpen={showModal}
        onClose={closeModal}
        title={editRequest ? 'Chỉnh sửa đơn từ' : 'Tạo đơn xin phép mới'}
        size="md"
        footer={
          <>
            <button onClick={closeModal} className="btn-secondary">Hủy</button>
            <button onClick={handleSubmit} disabled={isMutating} className="btn-primary">
              {isMutating ? <LoadingSpinner size="sm" /> : editRequest ? 'Lưu thay đổi' : 'Gửi đơn'}
            </button>
          </>
        }
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">Loại đơn</label>
            <select
              className="input-field"
              value={form.type}
              onChange={(e) => setForm({ ...form, type: e.target.value as RequestForm['type'] })}
            >
              {typeOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5">
                Từ ngày giờ <span className="text-red-500">*</span>
              </label>
              <input
                type="datetime-local"
                className={`input-field ${formErrors.start_datetime ? 'border-red-400' : ''}`}
                value={form.start_datetime}
                onChange={(e) => setForm({ ...form, start_datetime: e.target.value })}
              />
              {formErrors.start_datetime && (
                <p className="text-red-500 text-xs mt-1">{formErrors.start_datetime}</p>
              )}
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5">
                Đến ngày giờ <span className="text-red-500">*</span>
              </label>
              <input
                type="datetime-local"
                className={`input-field ${formErrors.end_datetime ? 'border-red-400' : ''}`}
                value={form.end_datetime}
                onChange={(e) => setForm({ ...form, end_datetime: e.target.value })}
              />
              {formErrors.end_datetime && (
                <p className="text-red-500 text-xs mt-1">{formErrors.end_datetime}</p>
              )}
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">
              Lý do <span className="text-red-500">*</span>
            </label>
            <textarea
              className={`input-field resize-none h-28 ${formErrors.reason ? 'border-red-400' : ''}`}
              value={form.reason}
              onChange={(e) => setForm({ ...form, reason: e.target.value })}
              placeholder="Nhập lý do xin phép..."
            />
            {formErrors.reason && (
              <p className="text-red-500 text-xs mt-1">{formErrors.reason}</p>
            )}
          </div>
          {(createMutation.isError || updateMutation.isError) && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-3">
              <p className="text-red-700 text-sm">
                {createMutation.error?.message || updateMutation.error?.message || 'Có lỗi xảy ra'}
              </p>
            </div>
          )}
        </div>
      </Modal>

      {/* Cancel Confirm Modal */}
      <Modal
        isOpen={!!cancelTarget}
        onClose={closeCancel}
        title="Hủy đơn từ"
        size="sm"
        footer={
          <>
            <button onClick={closeCancel} className="btn-secondary">Không</button>
            <button
              onClick={() => cancelTarget && cancelMutation.mutate(cancelTarget.id)}
              disabled={cancelMutation.isPending}
              className="btn-danger"
            >
              {cancelMutation.isPending ? <LoadingSpinner size="sm" /> : 'Hủy đơn'}
            </button>
          </>
        }
      >
        <div className="space-y-3">
          <p className="text-gray-600">
            Bạn có chắc muốn hủy đơn{' '}
            <span className="font-semibold">{cancelTarget ? typeLabel[cancelTarget.type] : ''}</span> này không?
          </p>
          {cancelMutation.isError && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-3">
              <p className="text-red-700 text-sm">
                {cancelMutation.error?.message || 'Hủy đơn thất bại'}
              </p>
            </div>
          )}
        </div>
      </Modal>
    </div>
  )
}

export default MyRequests

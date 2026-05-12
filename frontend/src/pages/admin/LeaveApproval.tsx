import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckCircle, XCircle, Eye } from 'lucide-react'
import { leaveApi } from '../../services/api'
import type { LeaveRequest } from '../../types'
import PageTitle from '../../components/PageTitle'
import Modal from '../../components/Modal'
import StatusBadge from '../../components/StatusBadge'
import LoadingSpinner from '../../components/LoadingSpinner'
import Pagination from '../../components/Pagination'
import { format } from 'date-fns'

type TabType = 'cho_duyet' | 'da_duyet' | 'tu_choi' | 'da_huy'

const tabs: { key: TabType; label: string }[] = [
  { key: 'cho_duyet', label: 'Chờ duyệt' },
  { key: 'da_duyet', label: 'Đã duyệt' },
  { key: 'tu_choi', label: 'Từ chối' },
  { key: 'da_huy', label: 'Đã hủy' },
]

const typeLabel: Record<string, string> = {
  nghi_phep: 'Nghỉ phép',
  di_muon: 'Đi muộn',
  ve_som: 'Về sớm',
}

const LeaveApproval: React.FC = () => {
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useState<TabType>('cho_duyet')
  const [page, setPage] = useState(1)
  const [viewRequest, setViewRequest] = useState<LeaveRequest | null>(null)
  const [rejectTarget, setRejectTarget] = useState<LeaveRequest | null>(null)
  const [rejectReason, setRejectReason] = useState('')
  const [rejectError, setRejectError] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['leave-requests', activeTab, page],
    queryFn: () => leaveApi.getAll({ status: activeTab, page, page_size: 15 }),
  })

  const approveMutation = useMutation({
    mutationFn: leaveApi.approve,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['leave-requests'] })
      queryClient.invalidateQueries({ queryKey: ['summary'] })
    },
  })

  const rejectMutation = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) =>
      leaveApi.reject(id, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['leave-requests'] })
      queryClient.invalidateQueries({ queryKey: ['summary'] })
      setRejectTarget(null)
      setRejectReason('')
    },
  })

  const requests: LeaveRequest[] = data?.data?.items || []
  const totalPages = data?.data?.total_pages || 1
  const totalItems = data?.data?.total || 0

  const handleTabChange = (tab: TabType) => {
    setActiveTab(tab)
    setPage(1)
  }

  const handleReject = () => {
    if (!rejectReason.trim()) {
      setRejectError('Vui lòng nhập lý do từ chối')
      return
    }
    setRejectError('')
    if (rejectTarget) {
      rejectMutation.mutate({ id: rejectTarget.id, reason: rejectReason })
    }
  }

  const formatDateTime = (dt: string) => {
    try {
      return format(new Date(dt), 'dd/MM/yyyy HH:mm')
    } catch {
      return dt
    }
  }

  return (
    <div>
      <PageTitle title="Quản lý Đơn từ" subtitle="Duyệt đơn xin nghỉ phép, đi muộn, về sớm" />

      {/* Tabs */}
      <div className="flex gap-1 bg-gray-100 p-1 rounded-xl mb-4 w-fit">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => handleTabChange(tab.key)}
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
                  <th className="table-header">Nhân viên</th>
                  <th className="table-header">Loại đơn</th>
                  <th className="table-header">Bắt đầu</th>
                  <th className="table-header">Kết thúc</th>
                  <th className="table-header">Lý do</th>
                  <th className="table-header">Ngày gửi</th>
                  <th className="table-header">Trạng thái</th>
                  <th className="table-header text-right">Thao tác</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {requests.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="py-12 text-center text-gray-400 text-sm">
                      Không có đơn nào
                    </td>
                  </tr>
                ) : (
                  requests.map((req) => (
                    <tr key={req.id} className="table-row">
                      <td className="table-cell font-medium">{req.employee?.full_name || `NV#${req.employee_id}`}</td>
                      <td className="table-cell">
                        <StatusBadge status={req.type} label={typeLabel[req.type]} />
                      </td>
                      <td className="table-cell text-sm text-gray-500">
                        {formatDateTime(req.start_datetime)}
                      </td>
                      <td className="table-cell text-sm text-gray-500">
                        {formatDateTime(req.end_datetime)}
                      </td>
                      <td className="table-cell max-w-xs">
                        <p className="truncate text-gray-600 text-sm">{req.reason}</p>
                      </td>
                      <td className="table-cell text-gray-500 text-sm">
                        {formatDateTime(req.created_at)}
                      </td>
                      <td className="table-cell">
                        <StatusBadge status={req.status} />
                      </td>
                      <td className="table-cell text-right">
                        <div className="flex items-center justify-end gap-1">
                          <button
                            onClick={() => setViewRequest(req)}
                            className="p-1.5 text-gray-500 hover:bg-gray-100 rounded-lg"
                            title="Xem chi tiết"
                          >
                            <Eye size={15} />
                          </button>
                          {req.status === 'cho_duyet' && (
                            <>
                              <button
                                onClick={() => approveMutation.mutate(req.id)}
                                disabled={approveMutation.isPending}
                                className="p-1.5 text-green-600 hover:bg-green-50 rounded-lg"
                                title="Duyệt"
                              >
                                <CheckCircle size={16} />
                              </button>
                              <button
                                onClick={() => {
                                  setRejectTarget(req)
                                  setRejectReason('')
                                  setRejectError('')
                                }}
                                className="p-1.5 text-red-500 hover:bg-red-50 rounded-lg"
                                title="Từ chối"
                              >
                                <XCircle size={16} />
                              </button>
                            </>
                          )}
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
          pageSize={15}
        />
      </div>

      {/* View Detail Modal */}
      <Modal
        isOpen={!!viewRequest}
        onClose={() => setViewRequest(null)}
        title="Chi tiết đơn từ"
        size="md"
        footer={
          <div className="flex gap-2 w-full justify-between">
            {viewRequest?.status === 'cho_duyet' && (
              <>
                <button
                  onClick={() => {
                    if (viewRequest) {
                      approveMutation.mutate(viewRequest.id)
                      setViewRequest(null)
                    }
                  }}
                  className="btn-success flex items-center gap-2"
                >
                  <CheckCircle size={16} />
                  Duyệt đơn
                </button>
                <button
                  onClick={() => {
                    setRejectTarget(viewRequest)
                    setViewRequest(null)
                    setRejectReason('')
                  }}
                  className="btn-danger flex items-center gap-2"
                >
                  <XCircle size={16} />
                  Từ chối
                </button>
              </>
            )}
            <button onClick={() => setViewRequest(null)} className="btn-secondary ml-auto">
              Đóng
            </button>
          </div>
        }
      >
        {viewRequest && (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-gray-50 rounded-lg p-3">
                <p className="text-xs text-gray-500 mb-1">Nhân viên</p>
                <p className="font-semibold text-gray-900">{viewRequest.employee?.full_name || `NV#${viewRequest.employee_id}`}</p>
              </div>
              <div className="bg-gray-50 rounded-lg p-3">
                <p className="text-xs text-gray-500 mb-1">Loại đơn</p>
                <StatusBadge status={viewRequest.type} label={typeLabel[viewRequest.type]} size="md" />
              </div>
              <div className="bg-gray-50 rounded-lg p-3">
                <p className="text-xs text-gray-500 mb-1">Từ</p>
                <p className="text-sm font-medium">{formatDateTime(viewRequest.start_datetime)}</p>
              </div>
              <div className="bg-gray-50 rounded-lg p-3">
                <p className="text-xs text-gray-500 mb-1">Đến</p>
                <p className="text-sm font-medium">{formatDateTime(viewRequest.end_datetime)}</p>
              </div>
            </div>
            <div className="bg-gray-50 rounded-lg p-3">
              <p className="text-xs text-gray-500 mb-1">Lý do</p>
              <p className="text-sm text-gray-700">{viewRequest.reason}</p>
            </div>
            {viewRequest.reject_reason && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-3">
                <p className="text-xs text-red-500 mb-1">Lý do từ chối</p>
                <p className="text-sm text-red-700">{viewRequest.reject_reason}</p>
              </div>
            )}
            <div className="flex items-center justify-between text-sm text-gray-500">
              <span>Ngày gửi: {formatDateTime(viewRequest.created_at)}</span>
              <StatusBadge status={viewRequest.status} />
            </div>
          </div>
        )}
      </Modal>

      {/* Reject Modal */}
      <Modal
        isOpen={!!rejectTarget}
        onClose={() => setRejectTarget(null)}
        title="Từ chối đơn từ"
        size="sm"
        footer={
          <>
            <button onClick={() => setRejectTarget(null)} className="btn-secondary">Hủy</button>
            <button onClick={handleReject} disabled={rejectMutation.isPending} className="btn-danger">
              {rejectMutation.isPending ? <LoadingSpinner size="sm" /> : 'Từ chối'}
            </button>
          </>
        }
      >
        <div className="space-y-3">
          <p className="text-gray-600 text-sm">
            Từ chối đơn của <strong>{rejectTarget?.employee?.full_name || `NV#${rejectTarget?.employee_id}`}</strong>
          </p>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">
              Lý do từ chối <span className="text-red-500">*</span>
            </label>
            <textarea
              className={`input-field resize-none h-24 ${rejectError ? 'border-red-400' : ''}`}
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="Nhập lý do từ chối..."
            />
            {rejectError && <p className="text-red-500 text-xs mt-1">{rejectError}</p>}
          </div>
        </div>
      </Modal>
    </div>
  )
}

export default LeaveApproval
